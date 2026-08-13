"""Contracts application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.contracts.domain.value_objects.contract_status import (
    CONTRACT_TRANSITIONS,
    TERMINAL_CONTRACT_STATUSES,
    ContractStatus,
)
from src.modules.contracts.infrastructure.repository import ContractsRepository
from src.modules.contracts.schemas.request import ContractRequest
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
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

    async def create(self, user_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        proposal = await self.repo.get_proposal(payload.proposal_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {payload.proposal_id} not found")
        if proposal.status != "accepted":
            raise BusinessRuleError(
                f"Contract can only be created from an accepted proposal "
                f"(current status: '{proposal.status}')"
            )

        version_number = await self.repo.count_by_deal(payload.deal_id) + 1

        client = await self.repo.get_client(payload.client_id)
        client_snapshot: dict = {}
        if client is not None:
            client_snapshot = {
                "id": str(client.id),
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
            }

        return await self.repo.create(
            deal_id=payload.deal_id,
            proposal_id=payload.proposal_id,
            client_id=payload.client_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=payload.content,
            client_snapshot=client_snapshot,
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

    async def update(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != "draft":
            raise BusinessRuleError(
                f"Contract content can only be edited in draft status "
                f"(current status: '{contract.status}')"
            )
        if payload.content:
            contract.content = payload.content
        return await self.repo.save(contract)

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

            # SINH TASK "Thu tiền:" NGAY TẠI ĐÂY — lúc ký, không đợi deal vào "active".
            #
            # Đợt đầu của mọi báo giá đều ghi "Khi ký hợp đồng / trước khi bắt đầu". Trước đây
            # task nhắc thu tiền chỉ sinh khi deal chuyển "active" (bấm "Bắt đầu triển khai"),
            # tức MỘT NHỊP SAU thời điểm phải thu: freelancer đã bắt tay làm rồi hệ thống mới
            # nhắc đi đòi cọc. Ngược đời, và đúng cái rủi ro SoloDesk sinh ra để ngăn.  #Huynh
            #
            # Idempotent (project đã có task thu tiền thì không sinh nữa) nên khối tương tự bên
            # `DealsService.transition_stage` VẪN GIỮ: hợp đồng ký từ trước ngày sửa này vẫn
            # được vá khi deal vào active, mà chuyển active sau đó không nhân đôi task.
            #
            # Import CỤC BỘ trong hàm, y như deals đang làm — tránh vòng import giữa các module.
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
        elif target == ContractStatus.PENDING_SIGNATURES or target in TERMINAL_CONTRACT_STATUSES:
            pass

        return await self.repo.save(contract)

    async def amend(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
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
            content=payload.content if payload.content else contract.content,
            client_snapshot=contract.client_snapshot,
            parent_contract_id=contract.id,
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
        body = template.content.get("body") if isinstance(template.content, dict) else None
        if isinstance(body, str) and body.strip():
            content = dict(content)
            content["standard_terms"] = body.strip()
        return content

    async def send(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "pending_signatures")

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
        return await self.repo.save(contract)

    async def terminate(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "terminated")

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

        return build_contract_document(
            contract, deal=deal, client=client, user=user, milestones=milestones
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

    async def generate_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> bytes:
        """Kết xuất PDF NGAY (đồng bộ) từ CÙNG document với bản xem trước — để freelancer
        tải về gửi khách. Cùng khuôn với proposals.generate_pdf (weasyprint).

        Khác `export_pdf` cũ: cái đó đẩy task Celery `render_contract_pdf` (đang là stub
        NotImplementedError) nên chưa chạy được. Ở đây render thẳng, không qua worker.  #Huynh
        """
        from src.ai.contract_generator.application.render import ContractPdfRenderer

        document = await self._build_document(user_id, contract_id)
        return ContractPdfRenderer().render_pdf(document)

    async def export_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> dict:
        from src.workers.pdf_jobs.tasks import render_contract_pdf

        contract = await self._get_contract(user_id, contract_id)

        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise EntitlementError("No active subscription found", "can_export_pdf")
        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None or not plan.can_export_pdf:
            raise EntitlementError(
                "Your subscription plan does not include PDF export", "can_export_pdf"
            )

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
