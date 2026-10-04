"""Contracts application service."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.contracts.application.proposal_terms import (
    apply_payment_from_proposal,
    apply_scope_from_proposal,
)
from src.modules.contracts.domain.value_objects.contract_status import (
    CONTRACT_TRANSITIONS,
    TERMINAL_CONTRACT_STATUSES,
    ContractStatus,
)
from src.modules.contracts.infrastructure.repository import (
    ContractsRepository,
    LiveContractExistsError,
    RowLockedError,
)
from src.modules.contracts.schemas.request import (
    CreateContractRequest,
    CreatePaymentMilestoneRequest,
    UpdateContractRequest,
    UpdatePaymentMilestoneRequest,
)
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.domain.template_blocks import apply_template_blocks, build_skeleton_content
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    ExpiredError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)

# Client-facing share link validity window — see proposals/application/service.py's
# matching constant for the reasoning; kept in sync at the same value.
SHARE_LINK_VALID_DAYS = 30

# Câu nói với người dùng khi `send` không giành được khoá ngay (xem `_lock_deal_then_contract`).
# 409 chứ không phải lỗi hệ thống: việc kia sắp xong, thử lại sau vài giây là được.
_MSG_BUSY = (
    "Hợp đồng này đang được gửi hoặc đang lưu ở một thao tác khác. Đợi vài giây rồi thử lại."
)

# Chỉ mục `uq_contracts_one_active_per_deal` cho phép mỗi deal tối đa MỘT hợp đồng chờ ký / đang
# hiệu lực. Câu này hiện thẳng cho freelancer nên nói rõ cách gỡ, không chỉ báo "bị chặn".
_MSG_LIVE_CONTRACT_EXISTS = (
    "Deal này đã có một hợp đồng khác đang chờ khách ký hoặc đang có hiệu lực, nên chưa gửi thêm "
    "hợp đồng mới được. Hãy hoàn tất hoặc đóng hợp đồng kia trước."
)


@dataclass
class ContractsService:
    db: AsyncSession
    repo: ContractsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ContractsRepository(self.db)

    async def _get_contract(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        contract = await self.repo.get_by_id(contract_id, user_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def _get_contract_for_update(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        """Như `_get_contract` nhưng KHOÁ HÀNG tới hết transaction.

        Dùng cho mọi thao tác SỬA hợp đồng nháp (nội dung, mốc thanh toán). `send` cũng khoá hàng
        này (xem `send`), nên một lượt sửa đến đúng lúc đang gửi phải ĐỨNG CHỜ rồi đọc lại thấy
        `pending_signatures` và bị từ chối — thay vì lọt qua kiểm tra `draft` bằng bản đọc cũ rồi
        ghi đè lên hợp đồng vừa được gửi đi. Không có khoá này, khách nhận PDF khác với bản đang
        lưu trong app.  #Huynh
        """
        contract = await self.repo.get_by_id_for_update(contract_id, user_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def _lock_deal_then_contract(  # type: ignore[no-untyped-def]
        self, user_id: uuid.UUID, contract_id: uuid.UUID, *, nowait: bool
    ):
        """Khoá DEAL rồi mới khoá HỢP ĐỒNG — trả hợp đồng đã đọc lại từ DB.

        Cùng khuôn với `ProposalsService._lock_deal_then_proposal`: deal luôn đứng TRƯỚC nên
        không có vòng chờ khoá, và khoá deal là thứ nối tiếp được hai hợp đồng nháp KHÁC NHAU của
        cùng một deal (chúng va vào chỉ mục `uq_contracts_one_active_per_deal` nếu cùng chạy).

        Cần biết `deal_id` trước khi khoá nên phải đọc hợp đồng một lượt không khoá. Không sao:
        `deal_id` không bao giờ đổi sau khi tạo, còn trạng thái thì được đọc LẠI sau khi đã giữ
        khoá (caller đừng dùng bản đọc không khoá để kiểm trạng thái).

        `nowait=True` (chỉ `send` dùng): không giành được khoá ngay thì báo 409 chứ không đứng
        chờ. `update` / milestones thì KHÔNG dùng nowait: hai lượt tự lưu liên tiếp phải xếp hàng
        chứ không được thất bại.  #Huynh
        """
        unlocked = await self.repo.get_by_id(contract_id, user_id)
        if unlocked is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        try:
            await self.repo.get_deal_for_update(unlocked.deal_id, user_id, nowait=nowait)
            contract = await self.repo.get_by_id_for_update(contract_id, user_id, nowait=nowait)
        except RowLockedError:
            raise BusinessRuleError(_MSG_BUSY) from None
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def create(self, user_id: uuid.UUID, payload: CreateContractRequest):  # type: ignore[return]
        proposal = await self.repo.get_proposal(payload.proposal_id)
        if proposal is None or proposal.owner_user_id != user_id:
            raise NotFoundError(f"Proposal {payload.proposal_id} not found")
        if proposal.status != "accepted":
            raise BusinessRuleError(
                f"Contract can only be created from an accepted proposal "
                f"(current status: '{proposal.status}')"
            )

        deal = await self.repo.get_deal(proposal.deal_id)
        if deal is None:
            raise NotFoundError(f"Deal {proposal.deal_id} not found")

        version_number = await self.repo.count_by_deal(deal.id) + 1

        client = await self.repo.get_client(deal.client_id)
        client_snapshot: dict = {}
        if client is not None:
            client_snapshot = {
                "id": str(client.id),
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
            }

        return await self.repo.create(
            deal_id=deal.id,
            proposal_id=payload.proposal_id,
            client_id=deal.client_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=payload.content,
            client_snapshot=client_snapshot,
            effective_date=payload.effective_date,
            end_date=payload.end_date,
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(
            user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
        )

    async def get_one(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self._get_contract(user_id, contract_id)

    async def update(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: UpdateContractRequest):  # type: ignore[return]
        contract = await self._get_contract_for_update(user_id, contract_id)
        if contract.status != "draft":
            raise BusinessRuleError(
                f"Contract content can only be edited in draft status "
                f"(current status: '{contract.status}')"
            )
        if payload.content is not None:
            contract.content = payload.content
        if payload.effective_date is not None:
            contract.effective_date = payload.effective_date
        if payload.end_date is not None:
            contract.end_date = payload.end_date
        return await self.repo.save(contract)

    async def list_milestones(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> list:
        await self._get_contract(user_id, contract_id)
        return await self.repo.get_milestones(contract_id)

    async def add_milestone(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: CreatePaymentMilestoneRequest
    ):  # type: ignore[return]
        contract = await self._get_contract_for_update(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"Milestones can only be added while the contract is in draft status "
                f"(current status: '{contract.status}')"
            )
        return await self.repo.create_milestone(
            contract_id=contract_id,
            description=payload.description,
            amount=payload.amount,
            due_date=payload.due_date,
            sort_order=payload.sort_order,
        )

    async def _get_milestone(self, user_id: uuid.UUID, contract_id: uuid.UUID, milestone_id: uuid.UUID):  # type: ignore[return]
        await self._get_contract(user_id, contract_id)
        milestone = await self.repo.get_milestone(milestone_id, contract_id)
        if milestone is None:
            raise NotFoundError(f"Milestone {milestone_id} not found")
        return milestone

    async def update_milestone(
        self,
        user_id: uuid.UUID,
        contract_id: uuid.UUID,
        milestone_id: uuid.UUID,
        payload: UpdatePaymentMilestoneRequest,
    ):  # type: ignore[return]
        contract = await self._get_contract_for_update(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"Milestones can only be edited while the contract is in draft status "
                f"(current status: '{contract.status}')"
            )
        milestone = await self._get_milestone(user_id, contract_id, milestone_id)
        if payload.description is not None:
            milestone.description = payload.description
        if payload.amount is not None:
            milestone.amount = payload.amount
        if payload.due_date is not None:
            milestone.due_date = payload.due_date
        if payload.sort_order is not None:
            milestone.sort_order = payload.sort_order
        return await self.repo.save_milestone(milestone)

    async def delete_milestone(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, milestone_id: uuid.UUID
    ) -> None:
        contract = await self._get_contract_for_update(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"Milestones can only be deleted while the contract is in draft status "
                f"(current status: '{contract.status}')"
            )
        milestone = await self._get_milestone(user_id, contract_id, milestone_id)
        await self.repo.delete_milestone(milestone)

    async def transition_status(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)

        try:
            current = ContractStatus(contract.status)
            target = ContractStatus(target_status)
        except ValueError:
            raise BusinessRuleError(f"'{target_status}' is not a valid contract status") from None

        if target not in CONTRACT_TRANSITIONS[current]:
            raise InvalidStateTransitionError("contract", current.value, target.value)

        now = datetime.now(UTC)
        contract.status = target.value

        if target == ContractStatus.ACTIVE:
            # KHÔNG cho ghi nhận đã ký khi deal chưa có báo giá nào được chấp nhận.
            #
            # Ký hợp đồng là CHỐT CUỐI (báo giá chỉ mới là chốt giá), và toàn bộ task thu tiền
            # sinh ra ngay dưới đây đọc từ bản báo giá `accepted` mới nhất. Không có bản nào thì
            # `billing_task_payloads_for_deal` trả rỗng và mọi thứ trôi qua LẶNG NGẮT: hợp đồng
            # thành "đang hiệu lực", không một task nào được tạo, và guard đóng dự án
            # (`if total > 0 and done < total`) cũng mất tác dụng vì `total == 0` luôn lọt.
            #
            # `DealsService.transition_stage` đã đòi đúng điều kiện này khi vào "active"
            # (deals/application/service.py:517) — cửa hợp đồng thì bỏ sót. Luật nghiệp vụ phải
            # đứng ở mọi cửa vào, không chỉ cửa nào ai đó nhớ ra trước.  #Huynh
            if not await self.repo.has_accepted_proposal(contract.deal_id, user_id):
                raise BusinessRuleError(
                    "Deal này chưa có báo giá nào được khách chấp nhận. Hãy ghi nhận khách "
                    "đã chấp nhận báo giá trước, vì các đợt thu tiền được tạo từ chính bản "
                    "báo giá đó."
                )

            # Freelancer GHI NHẬN rằng hai bên đã ký (ngoài hệ thống: giấy, scan, Zalo).
            #
            # Khách hàng của freelancer KHÔNG có tài khoản SoloDesk — bắt họ đăng ký để ký
            # một hợp đồng vài trăm nghìn là giết luôn tính năng. Nên hai bên ký ở ngoài,
            # freelancer vào đánh dấu. Đúng khuôn mẫu đã dùng cho báo giá
            # (PATCH /proposals/{id}/status — "ghi nhận phản hồi của khách bên ngoài").
            #
            # Bug cũ: chỗ này CHỈ ghi signed_by_freelancer_at. Hợp đồng thành "đang
            # hiệu lực" mà DB không có dấu vết nào cho thấy khách đã ký — hỏi "bằng
            # chứng đâu?" là bí. Giờ ghi cả hai mốc.
            #
            # LƯU Ý: đây là SỔ GHI NHẬN, không phải chữ ký số. SoloDesk không xác thực
            # danh tính người ký. Giao diện phải nói đúng như vậy, đừng gọi là "Khách ký".
            #   #Huynh
            if contract.signed_by_freelancer_at is None:
                contract.signed_by_freelancer_at = now
            if contract.signed_by_client_at is None:
                contract.signed_by_client_at = now
            await self._apply_active_side_effects(contract, user_id)
        elif target == ContractStatus.PENDING_SIGNATURES:
            contract.share_token = secrets.token_urlsafe(32)
            contract.share_expires_at = now + timedelta(days=SHARE_LINK_VALID_DAYS)
            # Bước duy nhất đẩy hợp đồng vào chỗ chỉ mục `uq_contracts_one_active_per_deal` canh
            # giữ. `send` đã hỏi trước (nên đây là lưới an toàn cho nó), nhưng `PATCH .../status`
            # đi thẳng vào đây không qua câu hỏi đó — và không khoá deal, nên hai lượt ghi nhận
            # cùng lúc vẫn có thể va nhau. Để chỉ mục từ chối thì ra 500; bắt lại để ra 409.
            try:
                return await self.repo.save_entering_live_status(contract)
            except LiveContractExistsError:
                raise BusinessRuleError(_MSG_LIVE_CONTRACT_EXISTS) from None
        elif target in TERMINAL_CONTRACT_STATUSES:
            pass

        return await self.repo.save(contract)

    async def _apply_active_side_effects(self, contract, user_id: uuid.UUID) -> None:
        """Project creation + payment tasks — must run once a contract has both signatures.

        SINH TASK "Thu tiền:" NGAY TẠI ĐÂY — lúc ký, không đợi deal vào "active".
        Đợt đầu của mọi báo giá đều ghi "Khi ký hợp đồng / trước khi bắt đầu". Trước đây
        task nhắc thu tiền chỉ sinh khi deal chuyển "active" (bấm "Bắt đầu triển khai"),
        tức MỘT NHỊP SAU thời điểm phải thu: freelancer đã bắt tay làm rồi hệ thống mới
        nhắc đi đòi cọc. Ngược đời, và đúng cái rủi ro SoloDesk sinh ra để ngăn.  #Huynh

        Idempotent (create_billing_tasks_for_entity bỏ qua title đã có) nên khối tương tự bên
        `DealsService.transition_stage` VẪN GIỮ: hợp đồng ký từ trước ngày sửa này vẫn
        được vá khi deal vào active, mà chuyển active sau đó không nhân đôi task — vì vậy
        an toàn khi được gọi từ nhiều nơi (freelancer tự đánh dấu, khách ký qua link công
        khai) mà không nhân đôi project/task.

        Import CỤC BỘ trong hàm, y như deals đang làm — tránh vòng import giữa các module.
        """
        from src.modules.projects.application.service import ProjectService
        from src.modules.proposals.application.service import (
            billing_task_payloads_for_deal,
        )
        from src.modules.tasks.application.service import TaskService

        deal = await self.repo.get_deal(contract.deal_id)
        project = await ProjectService(db=self.db).get_or_create_for_deal(
            contract.deal_id, user_id, name=deal.title if deal else None
        )
        payloads = await billing_task_payloads_for_deal(self.db, contract.deal_id, user_id)
        if payloads:
            await TaskService(self.db).create_billing_tasks_for_entity(
                "project", project.id, user_id, payloads
            )

    async def amend(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: UpdateContractRequest):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.ACTIVE:
            raise BusinessRuleError(
                f"Only active contracts can be amended (current status: '{contract.status}')"
            )

        new_version = await self.repo.count_by_deal(contract.deal_id) + 1

        new_contract = await self.repo.create(
            deal_id=contract.deal_id,
            proposal_id=contract.proposal_id,
            client_id=contract.client_id,
            owner_user_id=user_id,
            version_number=new_version,
            status=ContractStatus.DRAFT,
            content=payload.content if payload.content is not None else contract.content,
            client_snapshot=contract.client_snapshot,
            parent_contract_id=contract.id,
            effective_date=(
                payload.effective_date if payload.effective_date is not None else contract.effective_date
            ),
            end_date=payload.end_date if payload.end_date is not None else contract.end_date,
        )
        contract.status = ContractStatus.ARCHIVED
        await self.repo.save(contract)
        return new_contract

    async def generate_content(  # type: ignore[no-untyped-def]
        self,
        user_id: uuid.UUID,
        contract_id: uuid.UUID,
        ai_facade,
        *,
        template_id: uuid.UUID | None = None,
    ):
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"AI generation is only available for draft contracts (current status: '{contract.status}')"
            )

        # Cổng AI: kiểm tra gói (402), kiểm tra hạn mức tháng (429), ghi nhận lượt dùng.
        # Xem src/modules/subscriptions/application/ai_usage.py  #Huynh
        await AiUsageService(db=self.db).consume(user_id)

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        deal = await self.repo.get_deal(contract.deal_id)
        proposal = await self.repo.get_proposal(contract.proposal_id)
        client = await self.repo.get_client(contract.client_id)
        user = await self.repo.get_user(user_id)

        content = await ai_facade.generate_contract(
            deal_data={"title": deal.title if deal else "", "stage": deal.stage if deal else ""},
            proposal_content=proposal.content if proposal else {},
            client_data={
                "name": client.name if client else "",
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
                # Hợp đồng ghi bên cung cấp là hộ kinh doanh/công ty nếu freelancer có
                # đăng ký. Cột này đã có sẵn trong bảng users, chỉ là chưa ai truyền
                # xuống.  #Huynh
                "business_name": (user.business_name or "") if user else "",
            },
            user_can_use_ai=user_can_use_ai,
        )
        await AiUsageService(db=self.db).record_cost(
            user_id,
            ai_module="contract_generator",
            usage=ai_facade.last_usage("contract_generator"),
        )

        # Chèn điều khoản chuẩn từ mẫu freelancer CHỌN — NGUYÊN VĂN, AI không đụng tới. AI lo
        # phần thân (phạm vi, giá, mốc); điều khoản chuẩn giữ đúng chữ admin viết. Freelancer
        # sửa được khi review. Không chọn mẫu ("AI tự viết") thì để trống.  #Huynh
        content = await self._apply_chosen_template(
            content, template_id, user, template_type="contract"
        )

        # Tiền KHÔNG do AI quyết. Model từng tự viết lại các đợt thanh toán nên số từng đợt lệch
        # bảng hạng mục của báo giá (trong khi task thu tiền và hoá đơn bám đúng báo giá). Đoạn
        # thanh toán của model bị thay bằng câu dựng từ chính hạng mục chi phí; bảng các đợt do
        # `_build_document` suy ra từ cùng nguồn. Báo giá không có hạng mục nào thì giữ nguyên
        # chữ của model.  #Huynh
        content = apply_payment_from_proposal(
            content, proposal.content if proposal else None, replace_text=True
        )

        contract.content = content
        contract.ai_generated = True
        return await self.repo.save(contract)

    async def list_term_templates(self, user_id: uuid.UUID) -> list:
        """Mẫu điều khoản hợp đồng freelancer được chọn (theo nghề của họ + dùng chung)."""
        user = await self.repo.get_user(user_id)
        profession = getattr(user, "profession", None) if user else None
        return await self.repo.list_active_templates(
            template_type="contract", profession=profession
        )

    async def _apply_chosen_template(  # type: ignore[no-untyped-def]
        self, content: dict, template_id: uuid.UUID | None, user, *, template_type: str
    ) -> dict:
        if template_id is None:  # "AI tự viết" — không chèn mẫu
            return content
        profession = getattr(user, "profession", None) if user else None
        template = await self.repo.get_template_for_use(
            template_id, template_type=template_type, profession=profession
        )
        if template is None:
            # Mẫu không tồn tại / đã tắt / thuộc nghề khác — chặn, không im lặng bỏ qua.
            raise ValidationError("Mẫu điều khoản không hợp lệ hoặc không dùng được.")
        return apply_template_blocks(content, template.content, "contract")

    async def fill_from_template(  # type: ignore[no-untyped-def]
        self,
        user_id: uuid.UUID,
        contract_id: uuid.UUID,
        *,
        template_id: uuid.UUID | None = None,
    ):
        """Điền hợp đồng nháp từ KHUNG mẫu — KHÔNG gọi AI, KHÔNG tốn lượt.

        Cùng hình dạng với `generate_content` ngay trên, trừ hai thứ: không `AiUsageService` và
        không gọi model. Trước bản này, freelancer gói Free đứng ở bước thương lượng là bí đường
        hẳn — mọi nút tạo hợp đồng đều bắn request AI và trả về 402, không có lối nào khác.

        `template_id = None` = "khung trắng": hợp đồng giữ nguyên phần văn bản cứng của tờ giấy
        (căn cứ, quyền/nghĩa vụ, bảo mật, tranh chấp) và để trống các điều cần freelancer tự
        điền.  #Huynh
        """
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"Chỉ điền được nội dung cho hợp đồng ở trạng thái nháp "
                f"(hiện tại: '{contract.status}')"
            )

        content: dict = {}
        if template_id is not None:
            user = await self.repo.get_user(user_id)
            profession = getattr(user, "profession", None) if user else None
            template = await self.repo.get_template_for_use(
                template_id, template_type="contract", profession=profession
            )
            if template is None:
                raise ValidationError("Mẫu điều khoản không hợp lệ hoặc không dùng được.")
            content = build_skeleton_content(template.content, "contract")

        # Mẫu là văn bản chung cho cả nghề, không biết dự án này làm gì và giá bao nhiêu. Phần đó
        # lấy từ BÁO GIÁ ĐÃ CHỐT bằng code (không cần AI): phạm vi công việc vào Điều 1, tổng
        # giá trị vào Điều 3. Bản trước bỏ qua báo giá nên hợp đồng ký xong không ghi số tiền
        # nào.  #Huynh
        proposal = await self.repo.get_proposal(contract.proposal_id)
        proposal_content = proposal.content if proposal else None
        content = apply_scope_from_proposal(content, proposal_content)
        content = apply_payment_from_proposal(content, proposal_content, replace_text=False)

        contract.content = content
        contract.ai_generated = False
        return await self.repo.save(contract)

    async def send(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        """Gửi hợp đồng cho khách ký: chuyển sang `pending_signatures` VÀ gửi email kèm PDF.

        Trước đây hàm này chỉ đổi trạng thái và không gửi gì cả, nên nút "Gửi cho khách ký" là
        một lời nói dối: khách không nhận được tờ hợp đồng nào mà hệ thống vẫn ghi "đã gửi cho
        khách ký". Giờ thư đi thật, cùng lối với `ProposalsService.send` và
        `InvoicesService.send`.

        **Gửi hỏng thì KHÔNG đánh dấu đã gửi.** Email được gửi SAU khi đã chuyển trạng thái trong
        phiên làm việc, nhưng nếu SMTP ném `EmailDeliveryError` thì lỗi bay lên route và
        `get_db_session` rollback toàn bộ — hợp đồng nằm nguyên ở `draft`, freelancer thấy lý do
        và gửi lại được.

        Khách PHẢI có email: kiểm TRƯỚC mọi thay đổi. PDF đính kèm cho MỌI gói — cổng
        `can_export_pdf` chỉ chặn đường TẢI về (xem `_require_pdf_entitlement`), còn gửi giấy
        tờ cho khách vẫn mở cho mọi gói.

        Chuyển trạng thái chạy TRƯỚC khi dựng PDF nên các luật chuyển trạng thái vẫn là cổng
        đầu tiên: hợp đồng không được phép gửi thì không bao giờ có thư nào đi.

        Hai lượt gửi đụng nhau (cùng hợp đồng, hoặc hai hợp đồng của cùng một deal) thì lượt đến
        sau nhận 409 ngay, không đứng chờ — xem `_lock_deal_then_contract`. Deal đã có hợp đồng
        khác đang chờ ký / có hiệu lực cũng là 409, không phải 500.  #Huynh
        """
        from src.ai.contract_generator.application.render import ContractPdfRenderer
        from src.modules.contracts.application.emails import build_contract_email
        from src.modules.reminders.application.delivery_service import build_footer
        from src.shared.email.addresses import looks_like_email
        from src.shared.email.filenames import attachment_filename
        from src.shared.email.smtp import send_email
        from src.shared.rate_limit.send_guards import chan_nhip_gui_giay_to

        # Chặn dồn dập TRƯỚC mọi việc khác (kể cả khoá hàng): mỗi lượt gửi là một lá thư thật dùng
        # chung hạn mức Gmail của hệ thống. Xem `send_guards`.
        chan_nhip_gui_giay_to(user_id)

        # KHOÁ HÀNG trước khi đọc trạng thái — deal TRƯỚC, hợp đồng SAU, và KHÔNG ĐỨNG CHỜ. Cùng
        # lý do với `ProposalsService.send`: thư đi trước khi commit, nên bấm đúp mà không có khoá
        # thì khách nhận hai tờ hợp đồng (đã đo: 5 request đồng thời = 5 thư); request trùng mà
        # đứng chờ thì giữ một kết nối DB suốt thời gian người gửi thật còn đợi máy chủ thư.
        #
        # Khoá cả DEAL vì hai hợp đồng nháp của cùng một deal gửi cùng lúc sẽ va vào chỉ mục
        # `uq_contracts_one_active_per_deal` (mỗi deal tối đa một hợp đồng chờ ký / đang hiệu
        # lực): lượt sau đứng chờ lượt trước — cả lúc nó gửi thư — rồi ăn lỗi toàn vẹn, ra 500.
        # Khoá deal thì lượt sau bị từ chối ngay hoặc thấy lượt trước đã commit và bị từ chối gọn
        # ở câu hỏi bên dưới.  #Huynh
        contract = await self._lock_deal_then_contract(user_id, contract_id, nowait=True)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                "Chỉ hợp đồng nháp mới gửi được. Hợp đồng này đã gửi cho khách hoặc đã có hiệu lực."
            )
        # Hỏi TRƯỚC khi chốt trạng thái hay dựng PDF: hợp đồng khác của deal đang chờ ký / có hiệu
        # lực thì chỉ mục chắc chắn từ chối, mà đến lúc đó thì không thể làm gì nữa ngoài báo lỗi.
        if await self.repo.get_live_contract_for_deal(contract.deal_id, contract.id) is not None:
            raise BusinessRuleError(_MSG_LIVE_CONTRACT_EXISTS)

        client = await self.repo.get_client(contract.client_id)
        to_email = (getattr(client, "email", "") or "").strip()
        if not to_email:
            raise BusinessRuleError(
                "Khách hàng của hợp đồng này chưa có email, chưa gửi được. "
                "Bổ sung email cho khách rồi gửi lại."
            )
        if not looks_like_email(to_email):
            raise BusinessRuleError(
                f"Email của khách hàng ({to_email}) có vẻ không hợp lệ nên chưa gửi được. "
                "Sửa lại email khách rồi gửi lại."
            )

        contract = await self.transition_status(user_id, contract_id, "pending_signatures")

        document = await self._build_document(user_id, contract_id)
        pdf_bytes = ContractPdfRenderer().render_pdf(document)
        owner = await self.repo.get_user(user_id)

        content = build_contract_email(
            client_name=client.name,
            freelancer_name=getattr(owner, "full_name", None),
            project_name=document.project_name,
            contract_number=document.contract_number,
            footer=build_footer(
                getattr(owner, "full_name", None),
                getattr(owner, "email", None),
                document.project_name,
            ),
        )
        await send_email(
            to=to_email,
            subject=content.subject,
            html=content.html,
            plain=content.plain,
            from_name=getattr(owner, "full_name", None),
            reply_to=getattr(owner, "email", None),
            attachments=[
                (
                    attachment_filename("hop-dong", document.project_name),
                    pdf_bytes,
                    "application/pdf",
                )
            ],
        )
        return contract

    async def sign(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.PENDING_SIGNATURES:
            raise BusinessRuleError(
                f"Contract must be in pending_signatures status to sign "
                f"(current status: '{contract.status}')"
            )
        now = datetime.now(UTC)
        contract.signed_by_freelancer_at = now
        if contract.signed_by_client_at is not None:
            contract.status = ContractStatus.ACTIVE
            await self._apply_active_side_effects(contract, user_id)
        return await self.repo.save(contract)

    async def terminate(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "terminated")

    async def _get_by_share_token(self, share_token: str):  # type: ignore[return]
        contract = await self.repo.get_public_by_token(share_token)
        if contract is None:
            raise NotFoundError("Contract not found or link is invalid")
        return contract

    async def get_public_view(self, share_token: str):  # type: ignore[return]
        """Client-facing read view. 410s once the share link has expired."""
        contract = await self._get_by_share_token(share_token)
        if contract.share_expires_at is not None and datetime.now(UTC) > contract.share_expires_at:
            raise ExpiredError("This share link has expired")
        return contract

    async def sign_via_share_token(self, share_token: str, signer_name: str):  # type: ignore[return]
        """Client signs via the public link — no authenticated user_id.

        If the freelancer already signed via /contracts/{id}/sign, this is the second
        signature and the contract goes active immediately (same as the reverse order).
        """
        contract = await self._get_by_share_token(share_token)
        expired = (
            contract.share_expires_at is not None and datetime.now(UTC) > contract.share_expires_at
        )
        if expired or contract.status != ContractStatus.PENDING_SIGNATURES:
            raise BusinessRuleError(
                "This contract is not awaiting signature, or its share link has expired"
            )

        now = datetime.now(UTC)
        contract.signed_by_client_at = now
        content = dict(contract.content or {})
        content["client_signature"] = {"signer_name": signer_name, "signed_at": now.isoformat()}
        contract.content = content
        if contract.signed_by_freelancer_at is not None:
            contract.status = ContractStatus.ACTIVE
            await self._apply_active_side_effects(contract, contract.owner_user_id)
        return await self.repo.save(contract)

    async def _build_document(self, user_id: uuid.UUID, contract_id: uuid.UUID):
        """Dựng ContractDocument — DÙNG CHUNG cho HTML preview và (sau này) PDF.

        Tách riêng để bản trên màn hình và bản khách nhận render từ ĐÚNG MỘT document.
        Nếu hai bên tự dựng lấy thì kiểu gì cũng có ngày lệch — mà tờ hợp đồng trên màn
        hình khác tờ khách ký là thứ khiến hệ thống nhìn như lừa đảo. Cùng khuôn mẫu với
        proposals._build_document.  #Huynh
        """
        from src.modules.contracts.application.contract_content import (
            build_contract_document,
        )

        contract = await self._get_contract(user_id, contract_id)
        deal = await self.repo.get_deal(contract.deal_id)
        client = await self.repo.get_client(contract.client_id)
        user = await self.repo.get_user(user_id)
        milestones = await self.repo.get_milestones(contract.id)
        proposal = await self.repo.get_proposal(contract.proposal_id)

        return build_contract_document(
            contract,
            deal=deal,
            client=client,
            user=user,
            milestones=milestones,
            proposal_content=proposal.content if proposal else None,
        )

    async def render_preview_html(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, *, editable: bool = False
    ) -> str:
        """HTML xem trước — CHÍNH XÁC những gì bản PDF sẽ in ra. Frontend nhúng iframe.

        `editable=True` (bản nháp): render thêm ô rỗng cho các điều khoản chưa có, để sửa
        tại chỗ. Bản đọc-only/PDF thì để False.  #Huynh
        """
        from src.ai.contract_generator.application.render import ContractPdfRenderer

        document = await self._build_document(user_id, contract_id)
        return ContractPdfRenderer().render_html(document, editable=editable)

    async def _require_pdf_entitlement(self, user_id: uuid.UUID) -> None:
        """Cổng "Cho phép xuất PDF" của gói — gọi TRƯỚC khi render bất cứ tờ PDF nào.

        Trước đây khối kiểm này chỉ nằm trong `export_pdf`, tức đường Celery mà web không hề
        gọi, nên công tắc admin bật hay tắt đều như nhau: người dùng gói Free vẫn tải PDF bình
        thường qua GET /contracts/{id}/pdf. Tách ra đây để đường tải THẬT cũng phải đi qua
        đúng một cổng.

        Câu lỗi để tiếng Việt vì nó hiện thẳng cho freelancer (EntitlementError → HTTP 402).
        #Huynh
        """
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise EntitlementError(
                "Bạn chưa có gói đăng ký nào đang hoạt động nên chưa xuất được PDF.",
                "can_export_pdf",
            )
        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None or not plan.can_export_pdf:
            raise EntitlementError(
                "Gói của bạn chưa có tính năng xuất PDF. Hãy nâng cấp gói để tải bản PDF.",
                "can_export_pdf",
            )

    async def generate_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> bytes:
        """Kết xuất PDF NGAY (đồng bộ) từ CÙNG document với bản xem trước — để freelancer
        tải về gửi khách. Cùng khuôn với proposals.generate_pdf (weasyprint).

        Khác `export_pdf` cũ: cái đó đẩy task Celery `render_contract_pdf` (đang là stub
        NotImplementedError) nên chưa chạy được. Ở đây render thẳng, không qua worker.

        Kiểm gói ĐẦU TIÊN, trước cả khi dựng document: đây mới là đường web thật sự gọi, nên
        thiếu nó thì cột `can_export_pdf` chỉ là trang trí.  #Huynh
        """
        from src.ai.contract_generator.application.render import ContractPdfRenderer

        await self._require_pdf_entitlement(user_id)
        document = await self._build_document(user_id, contract_id)
        return ContractPdfRenderer().render_pdf(document)

    async def export_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> dict:
        from src.workers.pdf_jobs.tasks import render_contract_pdf

        contract = await self._get_contract(user_id, contract_id)
        await self._require_pdf_entitlement(user_id)

        task = render_contract_pdf.delay(str(contract.id))
        return {"status": "pending", "task_id": task.id, "download_url": None}

    async def delete(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> None:
        contract = await self._get_contract(user_id, contract_id)
        if contract.status not in ("draft", "expired"):
            raise BusinessRuleError(
                f"Only draft or expired contracts can be deleted "
                f"(current status: '{contract.status}')"
            )
        await self.repo.delete(contract)
