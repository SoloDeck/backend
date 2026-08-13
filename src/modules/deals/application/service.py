"""Deals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.facade import AIFacade
from src.ai.lead_qualifier.scoring import (
    build_gap_summary,
    compute_readiness,
    compute_win_likelihood,
    level_from_score,
    normalize_price_range,
)
from src.integrations.storage.client import StorageClient
from src.modules.deals.domain.aggregates.deal_aggregate import DealAggregate
from src.modules.deals.domain.entities.deal import Deal
from src.modules.deals.domain.entities.deal_activity import DealActivityType
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence
from src.modules.deals.domain.value_objects.deal_stage import (
    STAGE_TRANSITIONS,
    TERMINAL_STAGES,
    DealStage,
)
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.modules.intake_form.professions import profession_label, profession_scam_hint
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from src.shared.rate_limit import FixedWindowRateLimiter

log = structlog.get_logger(__name__)

DOCUMENT_MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Basic per-link guard for the public, unauthenticated intake form. Process-local;
# a generous window so legitimate submissions are unaffected while a flood of
# automated posts to a single share link is throttled (returns HTTP 429).
_public_intake_limiter = FixedWindowRateLimiter(max_requests=20, window_seconds=60)

# --- Chốt chặn cho đường ĐÍNH KÈM công khai ------------------------------------------------
#
# Đây là endpoint KHÔNG cần đăng nhập mà lại NHẬN FILE — không khoá lại thì link biểu mẫu
# công khai thành kho chứa file miễn phí cho bất kỳ ai có link. Ba chốt, mỗi chốt chặn một
# kiểu lạm dụng khác nhau:
#   - nhịp gửi: 30 lượt/phút cho mỗi link (một lần gửi form hợp lệ tối đa 10 tệp nên vẫn thoải mái),
#   - cửa sổ thời gian: chỉ đính kèm được ngay sau khi gửi form, không quay lại nhét file sau,
#   - trần số tệp: một deal không nhận quá 10 tệp từ đường công khai.
# Giới hạn LOẠI file và DUNG LƯỢNG từng tệp đã có sẵn trong `DealAttachmentService`.  #Huynh
_public_attach_limiter = FixedWindowRateLimiter(max_requests=30, window_seconds=60)
PUBLIC_INTAKE_ATTACH_WINDOW_MINUTES = 15
PUBLIC_INTAKE_MAX_ATTACHMENTS = 10

# Fields the lead_qualifier prompt's schema requires (see src/ai/lead_qualifier/
# prompts/prompts.txt) but that _parse_output never validates the LLM actually
# returned — logged here so an incomplete AI response is visible, not silent.
_EXPECTED_QUALIFICATION_KEYS = frozenset(
    {
        "project_type",
        "budget_signal",
        "timeline_signal",
        "urgency_signal",
        "red_flags",
        "next_step",
        "detected_signals",
        "suggested_actions",
        "price_range_min",
        "price_range_max",
    }
)

# Hai tiêu đề này là GIAO KÈO giữa mã nguồn và prompt: `ai/lead_qualifier/prompts/system.txt`
# gọi tên chúng NGUYÊN VĂN để ra luật chấm điểm. Sửa chữ ở một phía mà quên phía kia thì luật
# trỏ vào một khối không tồn tại — AI không hề báo lỗi, nó chỉ lặng lẽ chấm sai. Có test khoá
# hai phía lại với nhau (`test_tieu_de_khoi_khop_voi_prompt`).  #Huynh
SCORED_BLOCK_HEADING = "## YÊU CẦU DỰ ÁN — DÙNG ĐỂ CHẤM ĐIỂM"
UPDATED_BLOCK_HEADING = "## KHÁCH TRẢ LỜI THÊM — MỚI HƠN, ƯU TIÊN HƠN KHỐI TRÊN"
EXCLUDED_BLOCK_HEADING = "## KHÔNG PHẢI LỜI KHÁCH — CẤM DÙNG ĐỂ CHẤM ĐIỂM"


@dataclass
class DealsService:
    db: AsyncSession
    ai_facade: AIFacade | None = None
    repo: DealsRepository | None = None
    storage: StorageClient | None = None
    # Tiêm được như repo/ai_facade để test không phải dựng DB thật.
    usage: AiUsageService | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = DealsRepository(self.db)
        if self.usage is None:
            self.usage = AiUsageService(db=self.db)

    async def _get_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        deal = await self.repo.get_by_id(deal_id, user_id)
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal

    async def _get_intake(
        self,
        user_id: uuid.UUID,
        intake_id: uuid.UUID,
    ):
        intake = await self.repo.get_intake_by_id(intake_id, user_id)

        if intake is None:
            raise NotFoundError(f"Deal intake {intake_id} not found")

        return intake

    async def create(self, user_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        client = await self.repo.get_client_by_id(payload.client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {payload.client_id} not found")
        return await self.repo.create(
            owner_user_id=user_id,
            client_id=payload.client_id,
            title=payload.title,
            stage=payload.stage,
            source=payload.source,
            estimated_value=payload.estimated_value,
            actual_value=payload.actual_value,
            currency=payload.currency,
            notes=payload.notes,
            desired_timeline=payload.desired_timeline,
            client_budget=payload.client_budget,
            project_type=payload.project_type,
            service_category=payload.service_category,
            pricing_tier=payload.pricing_tier,
            profession=payload.profession,
            profession_fields=payload.profession_fields,
        )

    async def create_public_intake(self, share_token: str, payload: PublicIntakeRequest):
        """Capture a lead submitted through the owner's public intake link.

        No authentication: the owner is resolved solely from the hard-to-guess
        `share_token` — or from the owner's vanity `profile_slug`, since the public
        page is reachable both ways. Creates a minimal prospect Client, a `new_lead`
        Deal (so it surfaces in the owner's pipeline / GET /deals) and a DealIntake
        holding the raw inquiry for later AI qualification (Package 3 — no scoring here).
        """
        # Throttle by the raw token first so both valid and invalid links are
        # rate-limited (basic abuse guard) before any DB work.
        _public_intake_limiter.check(share_token)

        owner = await self.repo.get_owner_by_public_link(share_token)
        if owner is None:
            raise NotFoundError("Intake form not found or link is invalid")

        # Đếm thêm một lượt theo chủ sở hữu: cùng một freelancer mở được bằng token LẪN
        # slug, đếm theo chuỗi thô thôi thì mỗi lối vào một rổ riêng, trần spam tăng gấp
        # đôi. Lượt gửi thật tiêu một suất ở cả hai rổ nên người dùng bình thường không
        # thấy khác gì.  #Huynh
        _public_intake_limiter.check(f"owner:{owner.id}")

        # Deduplicate: reuse an existing client when both name and phone match.
        client = None
        if payload.phone:
            client = await self.repo.find_client_by_name_and_phone(
                owner.id, payload.name, payload.phone
            )
        if client is None:
            client = await self.repo.create_client(
                owner_user_id=owner.id,
                type="individual",
                name=payload.name,
                email=payload.email,
                phone=payload.phone,
                status="prospect",
            )
        deal = await self.repo.create(
            owner_user_id=owner.id,
            client_id=client.id,
            title=payload.project_name or f"Intake — {payload.name}",
            stage="new_lead",
            source="inbound",
            currency=owner.currency,
            profession=payload.profession,
            profession_fields=payload.profession_fields,
        )
        intake = await self.repo.create_intake(
            owner_user_id=owner.id,
            client_id=client.id,
            # Gắn phiếu vào ĐÚNG deal vừa tạo. Thiếu dòng này là khách gửi form lần hai
            # thì deal cũ bị chấm điểm (và báo giá) bằng brief của dự án mới.  #Huynh
            deal_id=deal.id,
            inquiry_text=payload.inquiry_text or "",
            estimated_budget=payload.estimated_budget,
            desired_timeline=payload.desired_timeline,
            source="inbound",
        )

        # Báo cho freelancer biết có khách mới. Thiếu bước này thì deal nằm im trong cột
        # "Deal Mới" cho tới khi freelancer tự mở ra xem — deal nóng để vài ngày là mất
        # khách, mà cả điểm mạnh của sản phẩm là "AI chấm điểm NGAY khi khách gửi form".
        #
        # Ghi vào cùng transaction với deal: hoặc cả hai cùng có, hoặc cả hai cùng không.
        # Không thể có deal mà không có thông báo.  #Huynh
        from src.modules.notifications.application.service import NotificationService

        await NotificationService(db=self.db).notify_intake_submitted(
            owner_user_id=owner.id,
            deal_id=deal.id,
            client_name=payload.name,
            project_name=payload.project_name,
        )

        # Ngoài chuông in-app, GỬI EMAIL cho freelancer: nhiều người không mở app cả ngày,
        # deal nóng để lâu là mất khách. Best-effort — mail hỏng (SMTP lỗi, chưa cấu hình)
        # KHÔNG được làm hỏng việc nhận form của khách, nên nuốt lỗi và chỉ ghi log.
        #
        # GỬI NGAY, KHÔNG QUA HÀNG ĐỢI.
        #
        # Bản trước: có đính kèm thì hoãn 60 giây qua Celery cho tệp kịp lên rồi mới đếm.
        # Đo trên bản chạy thật thì worker trả về `Received unregistered task ... KeyError`
        # — worker đọc danh sách task LÚC KHỞI ĐỘNG, nên bất kỳ lần deploy nào mà worker
        # còn chạy code cũ là email rơi vào hố, im lặng y như lỗi ban đầu đang phải sửa.
        # Đổi một mắt xích gãy được lấy con số chính xác hơn một chút là lỗ vốn.
        #
        # Tệp đi SAU phiếu nên lúc này DB đếm ra 0; dùng số khách KHAI để nói "gửi kèm N
        # tệp". Số này client gửi lên nên KHÔNG dùng vào việc gì khác ngoài một dòng chữ,
        # và đã bị chặn ≤ 10 ở tầng schema.  #Huynh
        await self.send_new_deal_email(
            owner.id, deal.id, declared_attachments=payload.attachment_count
        )

        from src.workers.ai_jobs.tasks import qualify_deal_async_by_id

        qualify_deal_async_by_id.delay(str(owner.id), str(deal.id))

        return intake

    async def add_public_intake_attachment(  # type: ignore[no-untyped-def]
        self,
        share_token: str,
        intake_id: uuid.UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ):
        """Khách đính tệp vào phiếu vừa gửi — KHÔNG cần đăng nhập.

        Vì sao phải có: form công khai vốn đã có khu kéo-thả tệp và hứa "PDF, Word, Excel,
        hình ảnh" với khách, nhưng phía gửi chỉ POST JSON còn `PublicIntakeRequest` không có
        chỗ chứa tệp — khách kéo tệp vào, bấm gửi, tưởng xong, thực tế tệp bị vứt im lặng.

        Chủ sở hữu suy từ `share_token` y như lúc gửi form; phiếu phải thuộc đúng chủ đó.
        Việc lưu trữ giao NGUYÊN cho `DealAttachmentService` (đã kiểm loại tệp, dung lượng,
        bóc chữ PDF cho AI đọc) — không viết lại một dòng nào của phần đó.  #Huynh
        """
        _public_attach_limiter.check(share_token)

        owner = await self.repo.get_owner_by_public_link(share_token)
        if owner is None:
            raise NotFoundError("Intake form not found or link is invalid")

        # Gộp rổ đếm theo chủ sở hữu, cùng lý do như lúc gửi form: token và slug là hai
        # lối vào của cùng một người.
        _public_attach_limiter.check(f"owner:{owner.id}")

        intake = await self.repo.get_intake_by_id(intake_id, owner.id)
        if intake is None or intake.deal_id is None:
            raise NotFoundError(f"Deal intake {intake_id} not found")

        # Chỉ nhận tệp NGAY SAU khi gửi form. Quá cửa sổ này thì link công khai không còn là
        # "đang gửi form" nữa, mà là một đường ghi tuỳ ý vào deal của người khác.
        submitted = intake.submitted_at or intake.created_at
        if submitted is not None:
            age = datetime.now(UTC) - submitted
            if age > timedelta(minutes=PUBLIC_INTAKE_ATTACH_WINDOW_MINUTES):
                raise BusinessRuleError(
                    "Đã quá thời gian đính kèm tệp cho yêu cầu này. "
                    "Vui lòng gửi lại biểu mẫu kèm tệp."
                )

        from src.modules.deals.application.attachment_service import DealAttachmentService

        service = DealAttachmentService(db=self.db)
        existing = await service.list_for_deal(owner.id, intake.deal_id)
        if len(existing) >= PUBLIC_INTAKE_MAX_ATTACHMENTS:
            raise BusinessRuleError(
                f"Mỗi yêu cầu chỉ nhận tối đa {PUBLIC_INTAKE_MAX_ATTACHMENTS} tệp."
            )

        return await service.upload(
            owner.id,
            intake.deal_id,
            filename=filename,
            content_type=content_type,
            data=data,
        )

    async def send_new_deal_email(
        self,
        owner_user_id: uuid.UUID,
        deal_id: uuid.UUID,
        *,
        declared_attachments: int = 0,
    ) -> bool:
        """Gửi thư báo có deal mới cho freelancer. Trả `True` nếu thư đã đi.

        Thông tin khách đọc lại từ DB (không nhận qua tham số) để thư luôn khớp với thứ
        freelancer sẽ thấy khi bấm vào link.

        SỐ TỆP thì lấy số LỚN HƠN giữa "đã nằm trong DB" và "khách khai sắp gửi": thư gửi
        ngay lúc nhận form, mà tệp thì tải lên sau đó vài giây — chỉ đọc DB là luôn ra 0.

        Best-effort: SMTP hỏng KHÔNG được làm hỏng việc nhận form của khách.  #Huynh
        """
        owner = await self.repo.get_owner_by_id(owner_user_id)
        if owner is None or not owner.email:
            log.warning(
                "intake.owner_email_skipped", owner_id=str(owner_user_id), reason="no_email"
            )
            return False

        deal = await self.repo.get_by_id(deal_id, owner_user_id)
        if deal is None:
            return False

        client = await self.repo.get_client_by_id(deal.client_id, owner_user_id)
        intake = await self.repo.get_intake_for_deal(deal_id, deal.client_id, owner_user_id)

        from src.config.settings import settings
        from src.modules.deals.application.attachment_service import DealAttachmentService
        from src.modules.deals.application.emails import build_new_deal_email
        from src.shared.email.smtp import send_email

        attachments = await DealAttachmentService(db=self.db).list_for_deal(owner_user_id, deal_id)
        attachment_count = max(len(attachments), declared_attachments)

        content = build_new_deal_email(
            owner_name=owner.full_name,
            client_name=client.name if client else "Khách hàng",
            project_name=deal.title,
            deal_url=f"{settings.frontend_url.rstrip('/')}/deals/{deal_id}",
            client_email=getattr(client, "email", None),
            client_phone=getattr(client, "phone", None),
            budget=getattr(intake, "estimated_budget", None),
            timeline=getattr(intake, "desired_timeline", None),
            inquiry_text=getattr(intake, "inquiry_text", None),
            attachment_count=attachment_count,
        )
        try:
            await send_email(
                to=owner.email,
                subject=content.subject,
                html=content.html,
                plain=content.plain,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, không chặn luồng intake
            log.warning(
                "intake.owner_email_failed",
                owner_id=str(owner_user_id),
                deal_id=str(deal_id),
                error=str(exc),
            )
            return False

        # PHẢI có log lúc THÀNH CÔNG. Bản trước chỉ log khi lỗi, nên lúc freelancer báo
        # "không nhận được mail" thì không phân biệt nổi *gửi rồi mà thất lạc* với *chưa
        # từng chạy* — mất cả buổi đoán mò.  #Huynh
        log.info(
            "intake.owner_email_sent",
            owner_id=str(owner_user_id),
            deal_id=str(deal_id),
            attachments=attachment_count,
        )
        return True

    async def list_all(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        stage: str | None = None,
        client_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(
            user_id, title=title, stage=stage, client_id=client_id, page=page, page_size=page_size
        )

    async def list_intakes(
        self, user_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list, int]:
        return await self.repo.list_intakes(user_id, page=page, page_size=page_size)

    async def get_intake(self, user_id: uuid.UUID, intake_id: uuid.UUID):
        intake = await self._get_intake(user_id, intake_id)
        return intake

    async def get_one(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_deal(user_id, deal_id)

    async def update(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        for field in (
            "title",
            "source",
            "estimated_value",
            "actual_value",
            "currency",
            "notes",
            "desired_timeline",
            "client_budget",
            "project_type",
            "service_category",
            "pricing_tier",
            "profession",
            "profession_fields",
        ):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(deal, field, value)
        return await self.repo.save(deal)

    async def delete(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> None:
        deal = await self._get_deal(user_id, deal_id)
        deal.deleted_at = datetime.now(UTC)
        await self.repo.save(deal)

    async def upload_document(
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
        *,
        filename: str,
        content: bytes,
        content_type: str,
    ):  # type: ignore[return]
        if self.storage is None:
            raise RuntimeError("Storage client not initialized")
        if content_type != "application/pdf":
            raise ValidationError(f"Unsupported file type '{content_type}'. Only PDF is allowed.")
        if not content:
            raise ValidationError("Document file is empty")
        if len(content) > DOCUMENT_MAX_SIZE_BYTES:
            raise ValidationError("Document must be 20MB or smaller")

        deal = await self._get_deal(user_id, deal_id)
        key = f"deals/{deal_id}/documents/{uuid.uuid4().hex}.pdf"
        deal.document_url = await self.storage.upload(
            key=key, content=content, content_type=content_type
        )
        deal.document_filename = filename
        saved = await self.repo.save(deal)
        await self.repo.create_activity_entry(
            deal_id=deal_id,
            owner_user_id=user_id,
            entry_type=DealActivityType.DOCUMENT_ATTACHED.value,
            description=f"Document attached: {filename}",
        )
        return saved

    async def transition_stage(
        self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealStageRequest
    ):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        try:
            current = DealStage(deal.stage)
            target = DealStage(payload.stage)
        except ValueError as exc:
            raise BusinessRuleError("Invalid deal stage") from exc
        if target not in STAGE_TRANSITIONS.get(current, frozenset()):
            raise InvalidStateTransitionError("deal", deal.stage, payload.stage)
        if target == DealStage.ACTIVE:
            if not await self.repo.has_accepted_proposal(deal_id, user_id):
                raise BusinessRuleError("Transitioning to active requires an accepted proposal")
            # Không cho bắt tay làm việc khi chưa có hợp đồng đã ký.
            #
            # Trước đây chỗ này CHỈ đòi báo giá được chấp nhận. Freelancer triển khai dự án
            # mà không có hợp đồng nào — đúng cái rủi ro SoloDesk sinh ra để ngăn. Giao diện
            # có chặn (nút bị khoá), nhưng API thì không: gọi thẳng là qua. Luật nghiệp vụ
            # phải nằm ở backend, giao diện chỉ là lớp lịch sự.  #Huynh
            if not await self.repo.has_signed_contract(deal_id, user_id):
                raise BusinessRuleError(
                    "Transitioning to active requires a signed contract "
                    "(record the client's signature on the contract first)"
                )
        if target == DealStage.COMPLETED_AND_BILLED:
            # ĐÓNG DEAL KHI THU ĐỦ TIỀN — nay đo bằng TASK "Thu tiền:" thay cho hoá đơn.
            #
            # Từ Phase B, các mốc thanh toán của báo giá đã chốt tự sinh thành task "Thu
            # tiền:" trên PROJECT của deal khi vào active (xem nhánh ACTIVE bên dưới).
            # Freelancer tick xong từng mốc khi nhận tiền, nên "thu đủ" = mọi task thu tiền
            # đã done. Bỏ ràng buộc phải có hoá đơn (mục 7: không tạo hoá đơn tay nữa). Deal
            # cũ / không có mốc thu tiền (total = 0) thì không chặn — tránh khoá dữ liệu cũ.
            #
            # Task gắn vào PROJECT (không phải deal): bảng "Công việc" hiển thị theo project,
            # và guard phải soi đúng chỗ freelancer tick.  #Huynh
            from src.modules.projects.application.service import ProjectService
            from src.modules.tasks.application.service import TaskService

            project = await ProjectService(db=self.db).get_or_create_for_deal(
                deal_id, user_id, name=deal.title
            )
            total, done = await TaskService(self.db).payment_task_progress(
                "project", project.id, user_id
            )
            if total > 0 and done < total:
                raise BusinessRuleError(
                    f"Còn {total - done}/{total} mốc thu tiền chưa hoàn tất. "
                    "Hãy tick xong các mốc 'Thu tiền:' trước khi hoàn thành dự án."
                )

            # GHI LẠI GIÁ THẬT — đóng vòng lặp học của bộ định giá. Không còn hoá đơn để lấy
            # tổng, nên neo vào GIÁ ĐÃ CHỐT trên báo giá (`estimated_value`, do set_price ghi
            # cả vào deal). Không bắt gõ tay: con số này hệ thống đã biết.  #Huynh
            if deal.estimated_value:
                deal.actual_value = deal.estimated_value

        deal.stage = payload.stage
        if target in TERMINAL_STAGES and hasattr(deal, "closed_at"):
            deal.closed_at = datetime.now(UTC)
            await self.repo.cancel_pending_reminders(deal_id, user_id)
        saved = await self.repo.save(deal)
        # Design decision #3 (Phase 24): a deal entering `active` auto-provisions a
        # linked Project. We call ProjectService directly (in the same session /
        # transaction) and idempotently — re-running a transition never duplicates
        # the project. Project invariants stay owned by the projects domain.
        if target == DealStage.ACTIVE:
            from src.modules.projects.application.service import ProjectService
            from src.modules.proposals.application.service import (
                payment_task_payloads_for_deal,
            )
            from src.modules.tasks.application.service import TaskService

            project = await ProjectService(db=self.db).get_or_create_for_deal(
                deal_id, user_id, name=deal.title
            )
            # Mốc thanh toán của báo giá đã chốt → task "Thu tiền:" trên project. Idempotent
            # (bỏ title trùng) nên chuyển active nhiều lần cũng không nhân đôi.  #Huynh
            payloads = await payment_task_payloads_for_deal(self.db, deal_id, user_id)
            if payloads:
                await TaskService(self.db).create_many_for_entity(
                    "project", project.id, user_id, payloads
                )
        return saved

    async def _run_ai_qualification(self, deal_model, inquiry_context: str) -> dict:
        """Run AI lead qualification against inquiry_context and persist scores on deal_model."""
        # Trước đây chỗ này truyền thẳng `user_can_use_ai=True` kèm `# TODO: get from
        # subscriptions`. Nghĩa là AI chấm điểm deal MIỄN PHÍ cho mọi user, kể cả gói
        # `free` (can_use_ai = false). Lỗ thủng doanh thu, và hạn mức 50 lượt/tháng của
        # gói Pro cũng không ai đếm.
        #
        # `consume()` làm cả ba việc: kiểm tra gói (402), kiểm tra hạn mức (429), và GHI
        # NHẬN lượt dùng vào usage_records.  #Huynh
        await self.usage.consume(deal_model.owner_user_id)  # type: ignore[union-attr]

        # Nghề của freelancer (chủ deal) → ngữ cảnh cho AI: ước giá đúng nghề + cảnh báo
        # scam đặc thù nghề. Đổi slug -> nhãn + gợi ý scam Ở ĐÂY (tầng business) rồi mới
        # truyền chuỗi xuống AI — src/ai/ không được import ngược lên src/modules/.  #Huynh
        profession_slug = await self.repo.get_owner_profession(  # type: ignore[union-attr]
            deal_model.owner_user_id
        )

        result = await self.ai_facade.qualify_lead(  # type: ignore[union-attr]
            inquiry_text=inquiry_context,
            user_can_use_ai=True,  # đã kiểm tra ở consume() ngay trên
            profession=profession_label(profession_slug),
            scam_hint=profession_scam_hint(profession_slug),
        )

        # Ghi token + chi phí ước tính vào ai_cost_records (màn hình admin đọc bảng này).
        await self.usage.record_cost(  # type: ignore[union-attr]
            deal_model.owner_user_id,
            ai_module="lead_qualifier",
            usage=self.ai_facade.last_usage("lead_qualifier"),  # type: ignore[union-attr]
        )

        missing_keys = sorted(
            key for key in _EXPECTED_QUALIFICATION_KEYS if result.get(key) is None
        )
        if missing_keys:
            log.warning(
                "deals.qualify_deal.incomplete_ai_output",
                deal_id=str(deal_model.id),
                missing_keys=missing_keys,
            )

        # Trước đây điểm chỉ là bảng tra ba nấc {"HOT": 80, "WARM": 50, "COLD": 20} —
        # AI không hề chấm điểm, nên deal 20 triệu và deal 700 nghìn đều ra đúng 50/100.
        # Giờ AI chấm TỪNG tiêu chí, backend cộng tổng (không giao phép cộng cho LLM),
        # và nhãn HOT/WARM/COLD suy ra TỪ điểm nên không bao giờ mâu thuẫn với nó.  #Huynh
        score, readiness_breakdown = compute_readiness(result.get("score_breakdown"))
        lead_level = level_from_score(score)
        result["suggested_lead_score"] = lead_level  # ghi đè nhãn model tự đoán
        result["score_breakdown"] = readiness_breakdown
        # Nửa còn lại của câu hỏi "vì sao có con điểm đó": vì sao MẤT phần điểm kia, và cần
        # gì để lên. Tra từ barem nên không tốn lượt AI nào.  #Huynh
        result["score_gaps"] = build_gap_summary(score, readiness_breakdown)

        _confidence_map = {
            "HOT": AIConfidence.high(),
            "WARM": AIConfidence.medium(),
            "COLD": AIConfidence.low(),
        }
        confidence = _confidence_map.get(lead_level, AIConfidence.medium())
        reasoning = str(result.get("reasoning", ""))
        # Trước ghi "gemma-4-31b-it" — SAI. Model chạy thật là llama-4-scout (xem
        # lead_qualifier/chain.py). Ghi sai model là ghi sai bằng chứng.  #Huynh
        model_version = "meta-llama/llama-4-scout-17b-16e-instruct"

        # Khả năng chốt deal — tính bằng CODE từ CHÍNH bảng phân rã ở trên, không hỏi AI
        # và không dò chuỗi trong câu văn của model.  #Huynh
        points = {item["key"]: item["points"] for item in readiness_breakdown}
        result["win_likelihood"] = compute_win_likelihood(
            budget_points=points.get("budget", 0),
            timeline_points=points.get("timeline", 0),
            detail_points=points.get("detail", 0),
            estimated_value=deal_model.estimated_value,
            price_range_min=result.get("price_range_min"),
            source=deal_model.source,
        )

        deal_domain = Deal(
            id=deal_model.id,
            owner_user_id=deal_model.owner_user_id,
            client_id=deal_model.client_id,
            title=deal_model.title,
            stage=DealStage(deal_model.stage),
            value=None,
            source=deal_model.source,
            expected_close_date=None,
            ai_score=deal_model.ai_qualification_score,
            ai_confidence=None,
            ai_recommendation=deal_model.ai_qualification_recommendation,
            closed_at=deal_model.closed_at,
            created_at=deal_model.created_at,
            updated_at=deal_model.updated_at,
            deleted_at=deal_model.deleted_at,
        )
        aggregate = DealAggregate(deal=deal_domain)
        lead_score = aggregate.score_lead(
            score=score,
            confidence=confidence.value,
            reasoning=reasoning,
            model_version=model_version,
        )

        detected_signals_raw = result.get("detected_signals")
        detected_signals = (
            [s if isinstance(s, dict) else s.model_dump() for s in detected_signals_raw]
            if detected_signals_raw
            else None
        )

        # Lưu CẢ PHẦN CHỨNG MINH vào lịch sử, không chỉ con số. `breakdown` (bảng căn cứ
        # chấm điểm) trước đây chỉ nằm ở localStorage của trình duyệt — đổi máy là mất.
        await self.repo.create_lead_score(
            id=lead_score.id,
            deal_id=lead_score.deal_id,
            score=lead_score.score,
            confidence=lead_score.confidence.value,
            reasoning=lead_score.reasoning,
            model_version=lead_score.model_version,
            generated_at=lead_score.generated_at,
            project_type=result.get("project_type"),
            budget_signal=result.get("budget_signal"),
            timeline_signal=result.get("timeline_signal"),
            urgency_signal=result.get("urgency_signal"),
            red_flags=result.get("red_flags"),
            breakdown=result.get("score_breakdown"),
            next_step=result.get("next_step"),
            detected_signals=detected_signals,
            prompt_version=result.get("prompt_version"),
        )

        deal_model.ai_qualification_score = lead_score.score
        deal_model.ai_qualification_confidence = lead_score.confidence.value
        deal_model.ai_qualification_recommendation = aggregate.deal.ai_recommendation
        deal_model.ai_qualification_reasoning = reasoning
        deal_model.ai_qualification_project_type = result.get("project_type")
        deal_model.ai_qualification_budget_signal = result.get("budget_signal")
        deal_model.ai_qualification_timeline_signal = result.get("timeline_signal")
        deal_model.ai_qualification_urgency_signal = result.get("urgency_signal")
        deal_model.ai_qualification_red_flags = result.get("red_flags")
        deal_model.ai_qualification_next_step = result.get("next_step")
        deal_model.ai_qualification_detected_signals = detected_signals
        deal_model.ai_qualification_suggested_actions = result.get("suggested_actions")
        # Model hay viết tắt "30 triệu" thành 30 → giao diện in ra "30 ₫". Chữa ở đây.
        price_low, price_high = normalize_price_range(
            result.get("price_range_min"), result.get("price_range_max")
        )
        result["price_range_min"] = price_low
        result["price_range_max"] = price_high
        deal_model.ai_qualification_price_range_min = price_low or None
        deal_model.ai_qualification_price_range_max = price_high or None
        await self.repo.save(deal_model)

        return {
            **result,
            "detected_signals": detected_signals,
            "ai_qualification_score": score,
            "ai_qualification_recommendation": aggregate.deal.ai_recommendation,
        }

    async def list_qualifications(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> list:
        """Lịch sử chấm điểm của deal — mới nhất trước.

        Mỗi lần chấm là một dòng RIÊNG, không ghi đè. Sửa deal rồi chấm lại thì bản cũ vẫn
        còn nguyên để đối chiếu — đó là lý do có bảng lịch sử.  #Huynh
        """
        await self._get_deal(user_id, deal_id)  # 404 nếu deal không phải của người này
        return await self.repo.list_lead_scores(deal_id, user_id)

    async def save_qualification(
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
        qualification_id: uuid.UUID | None = None,
        gap_acknowledged: bool = False,
    ):
        """Đóng dấu một bản chấm là ĐÃ CHỐT — đây là thứ tab "Tài liệu" hiển thị.

        Hai tab có vai trò khác nhau và trước đây không tài nào phân biệt được:

        * **Lịch sử** — MỌI lần bấm "Đánh giá", kể cả chấm thử rồi bỏ. Nguồn: mọi dòng
          `lead_scores`.
        * **Tài liệu** — CHỈ bản freelancer đã chủ động bấm "Lưu & chuyển sang Đã đánh giá".
          Nguồn: những dòng có `saved_at`.

        Không có mốc chốt riêng thì mỗi lần chấm nghịch lại đẻ thêm một "tài liệu", và tài
        liệu mất nghĩa. Trước đây nút Lưu chỉ đổi giai đoạn deal, không đánh dấu gì cả — nên
        giao diện báo "đã lưu vào tab Tài liệu" mà sang đó chẳng thấy gì.

        ``qualification_id`` = chốt ĐÚNG bản đó; bỏ trống thì chốt bản mới nhất.

        Bản đầu chỉ chốt được bản mới nhất, với lý do "bảng đánh giá luôn hiển thị lần chấm
        vừa xong nên hai thứ đó là một". Lý do ấy sai trong một luồng có thật: freelancer
        chấm xong QUÊN chốt rồi dọn mất tác vụ, sau đó vào tab Lịch sử mở lại bản cũ để chốt.
        Lúc này "bản đang xem" KHÔNG còn là "bản mới nhất" — chốt bản mới nhất là đóng dấu
        nhầm dòng, mà người dùng không hề biết. Không có đường này thì họ buộc phải chấm lại,
        tốn một lượt AI cho một kết quả đã có sẵn.

        Bù lại đúng như lo ngại ban đầu: nhận id từ ngoài thì phải kiểm id đó thuộc deal này
        và thuộc chủ sở hữu này — `get_lead_score_by_id` lọc cả ba vế.

        Bấm lưu nhiều lần thì mỗi lần là một mốc riêng; KHÔNG xoá dấu chốt của bản cũ. Người
        dùng chấm lại rồi chốt lại là có hai bản đã chốt thật, giống báo giá có nhiều phiên
        bản.

        ``gap_acknowledged`` = giao diện đã cảnh báo bản này chưa đủ 100 điểm và người dùng
        vẫn chọn chốt. Ghi lại vì nhìn một bản 27/100 đã chốt thì không phân biệt được "hệ
        thống để lọt" với "người dùng biết rõ và tự chịu trách nhiệm".  #Huynh
        """
        await self._get_deal(user_id, deal_id)  # 404 nếu deal không phải của người này

        if qualification_id is not None:
            target = await self.repo.get_lead_score_by_id(qualification_id, deal_id, user_id)
            if target is None:
                raise NotFoundError("Không tìm thấy bản đánh giá này trong deal")
        else:
            target = await self.repo.get_latest_lead_score(deal_id, user_id)
            if target is None:
                raise NotFoundError("Deal chưa có bản đánh giá nào để lưu")

        target.saved_at = datetime.now(UTC)
        target.gap_acknowledged = gap_acknowledged
        return await self.repo.save(target)

    async def _build_inquiry_context(self, deal_model, user_id: uuid.UUID) -> str:
        """Dựng ngữ cảnh gửi cho lead qualifier — HAI khối, và ranh giới nằm ĐÚNG chỗ.

        Bản trước chia "FREELANCER TỰ NHẬP" / "KHÁCH HÀNG NÓI GÌ", rồi xếp `deals.notes` vào
        khối đầu dưới nhãn "Ghi chú nội bộ". Nhãn đó SAI với chính sản phẩm: ô ấy trên giao
        diện tên là "Nội dung yêu cầu", màn hình chi tiết deal render nó thành "TỔNG QUAN DỰ
        ÁN", bảng dự án đọc nó làm `description`. Ghi chú riêng tư của freelancer nằm ở
        `clients.notes` — một cột KHÁC hẳn.

        Hậu quả đo được trên deal thật: cùng MỘT bản brief, gửi bằng file PDF thì chấm ngon,
        copy dán vào ô "Nội dung yêu cầu" thì chấm 12/100 — scope 12 "chỉ có tên dự án" dù
        chữ dán vào liệt kê 5 hạng mục, budget 0 dù có "Ngân sách: 700 triệu", timeline 0 dù
        có "Thời gian build: 5 tháng". Chữ không hề mất; nó chỉ bị dán nhãn sai.

        Người dùng gõ hay khách gõ thì YÊU CẦU vẫn là yêu cầu đó. Chính prompt đã viết ra
        nguyên tắc ấy ở tiêu chí `detail`: "đo YÊU CẦU được ghi lại kỹ tới đâu, KHÔNG đo ai
        là người gõ ra nó" — giờ áp cho cả 5 tiêu chí.

        Ranh giới THẬT chỉ có một: ô "Giá trị dự kiến" là con số FREELANCER TỰ ĐOÁN để ước
        doanh thu, khách chưa hề nói gì. Trước đây nó nằm lẫn trong danh sách phẳng dưới dạng
        "Estimated value: 200000 VND" và AI chấm 20/25 "khách cung cấp giá trị cụ thể". Nên
        khối 2 giờ chứa ĐÚNG một ô đó, và vắng mặt hẳn khi ô đó trống.  #Huynh
        """
        intake = await self.repo.get_intake_for_deal(deal_model.id, deal_model.client_id, user_id)
        attachments = await self.repo.list_attachments_with_text(deal_model.id, user_id)

        client_budget = getattr(intake, "estimated_budget", None) if intake else None
        client_timeline = getattr(intake, "desired_timeline", None) if intake else None

        # KHỐI 1 — mọi đường vào đều đổ về đây: gõ tay, biểu mẫu, hay file khách gửi kèm.
        requirement: list[str] = [f"- Tên dự án: {deal_model.title}"]
        if deal_model.source:
            requirement.append(f"- Nguồn deal: {deal_model.source}")
        if deal_model.project_type:
            requirement.append(f"- Loại dự án: {deal_model.project_type}")
        if deal_model.service_category:
            requirement.append(f"- Nhóm dịch vụ: {deal_model.service_category}")
        if deal_model.notes:
            # Nhãn TRÙNG KHÍT với chữ trên giao diện. Freelancer hỏi "AI có đọc ô Nội dung
            # yêu cầu của tôi không?" thì câu trả lời phải là có, đúng theo nghĩa đen.
            requirement.append(f"- Nội dung yêu cầu: {deal_model.notes}")
        if intake is not None and intake.inquiry_text:
            requirement.append(f"- Nội dung yêu cầu khách gửi qua biểu mẫu: {intake.inquiry_text}")
        for att in attachments:
            requirement.append(f"- Nội dung file khách gửi kèm ({att.filename}):")
            requirement.append(att.extracted_text or "")
        if client_budget:
            requirement.append(f"- Ngân sách khách nêu: {client_budget}")
        if client_timeline:
            requirement.append(f"- Thời gian khách muốn: {client_timeline}")

        # KHỐI 1B — thứ freelancer HỎI ĐƯỢC KHÁCH SAU khi đọc brief, ghi vào ô "Bổ sung
        # thông tin". Ưu tiên CAO HƠN brief.
        #
        # Vì sao phải tách riêng chứ không nối tiếp vào danh sách trên: brief có thể nói
        # ngược lại. Ca thật đã đo được — brief ghi "Về ngân sách thì bên mình chưa chốt con
        # số cụ thể", freelancer hỏi thêm rồi ghi "120 triệu", và AI chấm ngân sách 0 điểm
        # với lý do "khách chưa chốt con số". Nó không sai: hai dòng ngang hàng, brief nói
        # nhiều hơn nên thắng.
        #
        # Nhưng ĐÚNG ra thì dòng của freelancer phải thắng — brief là bản khách viết TRƯỚC,
        # còn đây là câu trả lời hỏi được SAU, thu thập đúng để lấp chỗ đang thiếu. Không có
        # thứ tự ưu tiên thì cả vòng "bổ sung rồi chấm lại" thành vô nghĩa.  #Huynh
        updates: list[str] = []
        if deal_model.client_budget:
            updates.append(f"- Ngân sách khách nêu: {deal_model.client_budget}")
        if deal_model.desired_timeline:
            updates.append(f"- Thời hạn khách nêu: {deal_model.desired_timeline}")

        # KHỐI 2 — ĐÚNG một ô, và ô này bị cấm chấm. Trống thì không in khối nào cả: một tiêu
        # đề rỗng chỉ tổ mời model đi tìm xem "khối kia" nằm ở đâu.
        excluded: list[str] = []
        if deal_model.estimated_value:
            excluded.append(
                f"- Giá trị dự kiến (FREELANCER TỰ ƯỚC, KHÔNG PHẢI KHÁCH BÁO): "
                f"{deal_model.estimated_value} {deal_model.currency}"
            )

        blocks: list[str] = [SCORED_BLOCK_HEADING, *requirement]
        if updates:
            blocks += ["", UPDATED_BLOCK_HEADING, *updates]
        if excluded:
            blocks += ["", EXCLUDED_BLOCK_HEADING, *excluded]
        return "\n".join(blocks)

    async def qualify_deal(
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
    ):
        deal_model = await self._get_deal(user_id, deal_id)

        if not self.ai_facade:
            raise RuntimeError("AIFacade not initialized")

        inquiry_context = await self._build_inquiry_context(deal_model, user_id)
        return await self._run_ai_qualification(deal_model, inquiry_context)
