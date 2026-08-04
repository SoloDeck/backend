import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from src.ai.shared.prompt import load_prompt
from src.modules.deals.application.service import (
    EXCLUDED_BLOCK_HEADING,
    SCORED_BLOCK_HEADING,
    DealsService,
)
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)


@dataclass
class DealStub:
    id: uuid.UUID
    stage: str
    client_id: uuid.UUID | None = None
    title: str = "Deal"
    closed_at: object | None = None
    document_url: str | None = None
    document_filename: str | None = None
    estimated_value: object | None = None
    actual_value: object | None = None


@dataclass
class OwnerStub:
    id: uuid.UUID
    currency: str = "VND"
    email: str | None = None
    full_name: str = "Owner"


async def test_create_requires_owned_client() -> None:
    repo = AsyncMock()
    repo.get_client_by_id.return_value = None
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(NotFoundError):
        await service.create(uuid.uuid4(), DealRequest(client_id=uuid.uuid4(), title="Deal"))


async def test_transition_rejects_backward_stage() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="in_negotiation")
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="proposal_sent")
        )


def test_giai_doan_rac_bi_chan_ngay_o_schema() -> None:
    """Giai đoạn rác là DỮ LIỆU KHÔNG HỢP LỆ (422), không phải xung đột trạng thái (409).

    Trước đây `target_stage` là `str` trần nên chuỗi rác lọt qua schema, xuống tới service
    mới bị chặn → trả 409 CONFLICT. Sai ngữ nghĩa: 409 nghĩa là "trạng thái hiện tại không
    cho phép", còn đây là "giá trị này không tồn tại". Giờ dùng enum, pydantic chặn ở cửa
    và FastAPI tự trả 422 kèm danh sách giá trị hợp lệ.  #Huynh
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DealStageRequest(target_stage="not_a_stage")


async def test_transition_to_active_requires_accepted_proposal() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="in_negotiation")
    repo.has_accepted_proposal.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active")
        )


def _patch_completion_services(project_id, progress):
    """Patch ProjectService + TaskService (import lười trong service) cho nhánh hoàn thành.

    Trả về context manager kép; `progress` = (tổng, đã xong) task 'Thu tiền:' của project."""
    proj_svc = AsyncMock()
    proj_svc.get_or_create_for_deal.return_value = SimpleNamespace(id=project_id)
    task_svc = AsyncMock()
    task_svc.payment_task_progress.return_value = progress
    return (
        patch(
            "src.modules.projects.application.service.ProjectService",
            return_value=proj_svc,
        ),
        patch(
            "src.modules.tasks.application.service.TaskService",
            return_value=task_svc,
        ),
    )


async def test_transition_to_completed_blocked_by_unfinished_payment_tasks() -> None:
    """Guard mới (Phase B): còn mốc 'Thu tiền:' chưa xong thì chưa cho hoàn thành."""
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=deal_id, stage="active")
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    proj_patch, task_patch = _patch_completion_services(uuid.uuid4(), (2, 1))
    with proj_patch, task_patch, pytest.raises(BusinessRuleError):
        await service.transition_stage(
            owner, deal_id, DealStageRequest(target_stage="completed_and_billed")
        )


async def test_transition_to_completed_allowed_when_payment_tasks_done() -> None:
    """Thu đủ (mọi mốc 'Thu tiền:' đã xong) → cho hoàn thành; actual_value = giá đã chốt."""
    deal_id = uuid.uuid4()
    owner = uuid.uuid4()
    deal = DealStub(id=deal_id, stage="active", estimated_value=30_000_000)
    repo = AsyncMock()
    repo.get_by_id.return_value = deal
    repo.save.side_effect = lambda d: d
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    proj_patch, task_patch = _patch_completion_services(uuid.uuid4(), (2, 2))
    with proj_patch, task_patch:
        result = await service.transition_stage(
            owner, deal_id, DealStageRequest(target_stage="completed_and_billed")
        )

    assert result.stage == "completed_and_billed"
    assert result.actual_value == 30_000_000


async def test_transition_from_terminal_stage_is_rejected() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="completed_and_billed")
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active")
        )


# ---------------------------------------------------------------------------
# upload_document
# ---------------------------------------------------------------------------


class TestUploadDocument:
    async def test_uploads_and_sets_document_url(self) -> None:
        deal_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        deal = DealStub(id=deal_id, stage="new_lead")
        repo = AsyncMock()
        repo.get_by_id.return_value = deal
        repo.save.side_effect = lambda d: d
        storage = AsyncMock()
        storage.upload.return_value = "https://cdn.example.com/deals/x/y.pdf"
        service = DealsService(db=AsyncMock(), repo=repo, storage=storage)

        result = await service.upload_document(
            owner_id,
            deal_id,
            filename="brief.pdf",
            content=b"%PDF-1.4 fake",
            content_type="application/pdf",
        )

        storage.upload.assert_awaited_once()
        assert result.document_url == "https://cdn.example.com/deals/x/y.pdf"
        assert result.document_filename == "brief.pdf"
        repo.create_activity_entry.assert_awaited_once()
        activity_kwargs = repo.create_activity_entry.await_args.kwargs
        assert activity_kwargs["entry_type"] == "document_attached"
        assert activity_kwargs["deal_id"] == deal_id
        assert activity_kwargs["owner_user_id"] == owner_id

    async def test_rejects_non_pdf_content_type(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = DealsService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_document(
                uuid.uuid4(),
                uuid.uuid4(),
                filename="image.png",
                content=b"fake-bytes",
                content_type="image/png",
            )
        storage.upload.assert_not_awaited()

    async def test_rejects_empty_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = DealsService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(ValidationError):
            await service.upload_document(
                uuid.uuid4(),
                uuid.uuid4(),
                filename="brief.pdf",
                content=b"",
                content_type="application/pdf",
            )

    async def test_rejects_oversized_file(self) -> None:
        repo = AsyncMock()
        storage = AsyncMock()
        service = DealsService(db=AsyncMock(), repo=repo, storage=storage)
        oversized = b"x" * (20 * 1024 * 1024 + 1)

        with pytest.raises(ValidationError):
            await service.upload_document(
                uuid.uuid4(),
                uuid.uuid4(),
                filename="brief.pdf",
                content=oversized,
                content_type="application/pdf",
            )

    async def test_raises_not_found_for_unknown_deal(self) -> None:
        repo = AsyncMock()
        repo.get_by_id.return_value = None
        storage = AsyncMock()
        service = DealsService(db=AsyncMock(), repo=repo, storage=storage)

        with pytest.raises(NotFoundError):
            await service.upload_document(
                uuid.uuid4(),
                uuid.uuid4(),
                filename="brief.pdf",
                content=b"%PDF-1.4",
                content_type="application/pdf",
            )

    async def test_raises_runtime_error_when_storage_not_initialized(self) -> None:
        repo = AsyncMock()
        service = DealsService(db=AsyncMock(), repo=repo)

        with pytest.raises(RuntimeError):
            await service.upload_document(
                uuid.uuid4(),
                uuid.uuid4(),
                filename="brief.pdf",
                content=b"%PDF-1.4",
                content_type="application/pdf",
            )


def _intake_payload(**overrides) -> PublicIntakeRequest:
    data = {"name": "Lead Person", "inquiry_text": "I need a landing page."}
    data.update(overrides)
    return PublicIntakeRequest(**data)


async def test_create_public_intake_creates_client_deal_and_intake() -> None:
    owner = OwnerStub(id=uuid.uuid4(), email="owner@example.com")
    client_id = uuid.uuid4()
    intake = IntakeStub(id=uuid.uuid4(), client_id=client_id)
    deal = DealStub(id=uuid.uuid4(), stage="new_lead", client_id=client_id)
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = owner
    repo.create_client.return_value = DealStub(id=client_id, stage="prospect")
    repo.create.return_value = deal
    repo.create_intake.return_value = intake
    # Thư báo deal mới đọc LẠI mọi thứ từ DB (xem `DealsService.send_new_deal_email`) để
    # đường gửi ngay và đường gửi hoãn qua Celery ra cùng một nội dung — nên mock phải trả
    # đủ chủ deal / deal / khách / phiếu.  #Huynh
    repo.get_owner_by_id.return_value = owner
    repo.get_by_id.return_value = deal
    repo.get_client_by_id.return_value = ClientStub(id=client_id)
    repo.get_intake_for_deal.return_value = intake

    # `Session.add()` là hàm ĐỒNG BỘ. Để AsyncMock tự sinh thì nó trả về một coroutine
    # không ai await → RuntimeWarning "coroutine was never awaited" và test đỏ vì một lý do
    # chẳng liên quan gì tới thứ đang được kiểm tra.  #Huynh
    db = AsyncMock()
    db.add = MagicMock()
    service = DealsService(db=db, repo=repo, usage=AsyncMock())

    # Unique token per test run so the shared process limiter is never the cause of failure.
    sent_email = AsyncMock()
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay", lambda *a: None)
        mp.setattr("src.shared.email.smtp.send_email", sent_email)
        # Đếm tệp đính kèm đụng object storage thật — ở tầng unit thì chặn lại.
        mp.setattr(
            "src.modules.deals.application.attachment_service.DealAttachmentService.list_for_deal",
            AsyncMock(return_value=[]),
        )
        result = await service.create_public_intake(f"tok-{uuid.uuid4().hex}", _intake_payload())

    assert result is intake
    # Owner có email -> phải gửi thông báo email "Deal mới" (ngoài chuông in-app).
    sent_email.assert_awaited_once()
    repo.create_client.assert_awaited_once()
    repo.create.assert_awaited_once()
    repo.create_intake.assert_awaited_once()
    # Deal is created under the resolved owner in the new_lead stage so it surfaces in GET /deals.
    deal_kwargs = repo.create.await_args.kwargs
    assert deal_kwargs["owner_user_id"] == owner.id
    assert deal_kwargs["stage"] == "new_lead"

    # Freelancer PHẢI được báo là có khách mới. Thiếu bước này thì deal nằm im trong cột
    # "Deal Mới" cho tới khi họ tự mở ra xem — deal nóng để vài ngày là mất khách.
    notification = db.add.call_args.args[0]
    assert notification.type == "intake_submitted"
    assert notification.user_id == owner.id
    assert notification.is_read is False


async def test_thu_bao_deal_moi_gui_NGAY_va_neu_so_tep_khach_khai() -> None:
    """Thư phải đi NGAY trong request nhận form, không qua hàng đợi.

    Đo trên bản chạy thật: bản trước hoãn thư 60 giây qua Celery cho tệp kịp lên rồi mới
    đếm — worker trả `Received unregistered task ... KeyError` vì nó đọc danh sách task lúc
    KHỞI ĐỘNG, nên message bị vứt và freelancer KHÔNG nhận được gì. Bất kỳ lần deploy nào
    mà worker còn chạy code cũ đều dính lại y hệt, và im lặng. Số tệp lấy theo con số khách
    khai (tệp tải lên sau, lúc này DB đếm ra 0).  #Huynh
    """
    owner = OwnerStub(id=uuid.uuid4(), email="owner@example.com")
    client_id = uuid.uuid4()
    deal = DealStub(id=uuid.uuid4(), stage="new_lead", client_id=client_id)
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = owner
    repo.create_client.return_value = DealStub(id=client_id, stage="prospect")
    repo.create.return_value = deal
    repo.create_intake.return_value = IntakeStub(id=uuid.uuid4(), client_id=client_id)
    repo.get_owner_by_id.return_value = owner
    repo.get_by_id.return_value = deal
    repo.get_client_by_id.return_value = ClientStub(id=client_id)
    repo.get_intake_for_deal.return_value = IntakeStub(id=uuid.uuid4(), client_id=client_id)

    db = AsyncMock()
    db.add = MagicMock()
    sent_email = AsyncMock()
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay", lambda *a: None)
        mp.setattr("src.shared.email.smtp.send_email", sent_email)
        mp.setattr(
            "src.modules.deals.application.attachment_service.DealAttachmentService.list_for_deal",
            AsyncMock(return_value=[]),
        )
        await DealsService(db=db, repo=repo, usage=AsyncMock()).create_public_intake(
            f"tok-{uuid.uuid4().hex}", _intake_payload(attachment_count=2)
        )

    # Gửi ngay trong chính lệnh gọi này, không hẹn giờ, không qua worker.
    sent_email.assert_awaited_once()
    body = sent_email.await_args.kwargs["plain"]
    assert "2 tệp" in body


class TestPublicIntakeAttachment:
    """Đường ĐÍNH KÈM công khai — không đăng nhập mà nhận file, nên phải khoá kỹ.

    Vì sao có đường này: form công khai vốn đã có khu kéo-thả tệp và hứa với khách "PDF,
    Word, Excel, hình ảnh", nhưng phía gửi chỉ POST JSON — tệp khách kéo vào bị vứt im
    lặng, không ai nhận.  #Huynh
    """

    @staticmethod
    def _service(repo: AsyncMock) -> DealsService:
        return DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    async def test_token_sai_thi_khong_nhan(self) -> None:
        repo = AsyncMock()
        repo.get_owner_by_intake_token.return_value = None

        with pytest.raises(NotFoundError):
            await self._service(repo).add_public_intake_attachment(
                f"bad-{uuid.uuid4().hex}",
                uuid.uuid4(),
                filename="brief.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
            )

    async def test_phieu_khong_thuoc_chu_link_thi_khong_nhan(self) -> None:
        # Chốt quan trọng nhất: có link hợp lệ KHÔNG có nghĩa được ghi vào phiếu bất kỳ.
        repo = AsyncMock()
        repo.get_owner_by_intake_token.return_value = OwnerStub(id=uuid.uuid4())
        repo.get_intake_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await self._service(repo).add_public_intake_attachment(
                f"tok-{uuid.uuid4().hex}",
                uuid.uuid4(),
                filename="brief.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
            )

    async def test_qua_cua_so_thoi_gian_thi_chan(self) -> None:
        from datetime import UTC, datetime, timedelta

        repo = AsyncMock()
        repo.get_owner_by_intake_token.return_value = OwnerStub(id=uuid.uuid4())
        repo.get_intake_by_id.return_value = SimpleNamespace(
            deal_id=uuid.uuid4(),
            submitted_at=datetime.now(UTC) - timedelta(hours=2),
            created_at=None,
        )

        # Quá cửa sổ thì link công khai không còn là "đang gửi form" nữa, mà thành một
        # đường ghi tuỳ ý vào deal của người khác.
        with pytest.raises(BusinessRuleError, match="quá thời gian"):
            await self._service(repo).add_public_intake_attachment(
                f"tok-{uuid.uuid4().hex}",
                uuid.uuid4(),
                filename="brief.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
            )

    async def test_qua_so_tep_toi_da_thi_chan(self) -> None:
        from datetime import UTC, datetime

        repo = AsyncMock()
        repo.get_owner_by_intake_token.return_value = OwnerStub(id=uuid.uuid4())
        repo.get_intake_by_id.return_value = SimpleNamespace(
            deal_id=uuid.uuid4(), submitted_at=datetime.now(UTC), created_at=None
        )

        with (
            patch(
                "src.modules.deals.application.attachment_service."
                "DealAttachmentService.list_for_deal",
                AsyncMock(return_value=[object()] * 10),
            ),
            pytest.raises(BusinessRuleError, match="tối đa"),
        ):
            await self._service(repo).add_public_intake_attachment(
                f"tok-{uuid.uuid4().hex}",
                uuid.uuid4(),
                filename="brief.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
            )

    async def test_hop_le_thi_giao_cho_dich_vu_dinh_kem_san_co(self) -> None:
        owner = OwnerStub(id=uuid.uuid4())
        deal_id = uuid.uuid4()
        from datetime import UTC, datetime

        repo = AsyncMock()
        repo.get_owner_by_intake_token.return_value = owner
        repo.get_intake_by_id.return_value = SimpleNamespace(
            deal_id=deal_id, submitted_at=datetime.now(UTC), created_at=None
        )
        upload = AsyncMock(return_value="saved")

        with patch(
            "src.modules.deals.application.attachment_service.DealAttachmentService.list_for_deal",
            AsyncMock(return_value=[]),
        ), patch(
            "src.modules.deals.application.attachment_service.DealAttachmentService.upload",
            upload,
        ):
            result = await self._service(repo).add_public_intake_attachment(
                f"tok-{uuid.uuid4().hex}",
                uuid.uuid4(),
                filename="brief.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4",
            )

        assert result == "saved"
        # Kiểm loại tệp / dung lượng / bóc chữ PDF đã nằm sẵn trong DealAttachmentService —
        # đường công khai dùng lại y nguyên, KHÔNG viết lại luật riêng.
        assert upload.await_args.args[0] == owner.id
        assert upload.await_args.args[1] == deal_id


async def test_create_public_intake_rejects_unknown_token() -> None:
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = None
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(NotFoundError):
        await service.create_public_intake(f"bad-{uuid.uuid4().hex}", _intake_payload())

    repo.create_client.assert_not_awaited()
    repo.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# qualify_deal — signal field mapping
# ---------------------------------------------------------------------------

_AI_RESULT = {
    "project_type": "E-commerce website",
    "budget_signal": "HIGH",
    "timeline_signal": "CLEAR",
    "urgency_signal": "MODERATE",
    "red_flags": ["no mockups provided"],
    "suggested_lead_score": "HOT",
    "reasoning": "Strong budget and clear timeline.",
    "next_step": "Reply today to confirm scope and move to quoting.",
    "detected_signals": [
        {"text": "Budget explicitly stated", "is_positive": True},
        {"text": "Timeline is clear", "is_positive": True},
        {"text": "No mockups provided", "is_positive": False},
    ],
    "suggested_actions": [
        "Reply today to confirm scope",
        "Generate AI quote after scope confirmation",
        "Set follow-up reminder in 24 hours",
    ],
    "price_range_min": 10000000,
    "price_range_max": 25000000,
}


@dataclass
class IntakeStub:
    id: uuid.UUID
    client_id: uuid.UUID
    inquiry_text: str = "I need a website built."
    estimated_budget: str | None = None
    desired_timeline: str | None = None


@dataclass
class ClientStub:
    """Khách hàng — thư báo deal mới lấy tên/email/SĐT từ đây."""

    id: uuid.UUID
    name: str = "Lead Person"
    email: str | None = None
    phone: str | None = None


@dataclass
class DealModelStub:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    title: str = "Test Deal"
    stage: str = "new_lead"
    source: str | None = None
    notes: str | None = None
    estimated_value: object | None = None
    currency: str = "VND"
    desired_timeline: str | None = None
    project_type: str | None = None
    service_category: str | None = None
    pricing_tier: str | None = None
    profession: str | None = None
    profession_fields: dict | None = None
    ai_qualification_score: int | None = None
    ai_qualification_confidence: float | None = None
    ai_qualification_recommendation: str | None = None
    ai_qualification_reasoning: str | None = None
    ai_qualification_project_type: str | None = None
    ai_qualification_budget_signal: str | None = None
    ai_qualification_timeline_signal: str | None = None
    ai_qualification_urgency_signal: str | None = None
    ai_qualification_red_flags: list | None = None
    ai_qualification_detected_signals: list | None = None
    ai_qualification_suggested_actions: list | None = None
    ai_qualification_next_step: str | None = None
    ai_qualification_price_range_min: int | None = None
    ai_qualification_price_range_max: int | None = None
    closed_at: object | None = None
    created_at: object | None = None
    updated_at: object | None = None
    deleted_at: object | None = None


@dataclass
class AttachmentStub:
    """File khách gửi kèm ĐÃ bóc được chữ — chỉ loại này mới đưa cho AI đọc."""

    filename: str
    extracted_text: str | None


def _make_qualify_service(
    ai_result: dict,
    *,
    # Giữ NGUYÊN mặc định cũ để 8 chỗ gọi sẵn có không đổi hành vi.
    intake_text: str | None = "I need a website built.",
    attachments: list | None = None,
    **deal_fields,
):
    client_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    intake = IntakeStub(id=uuid.uuid4(), client_id=client_id, inquiry_text=intake_text)
    deal_model = DealModelStub(
        id=deal_id, owner_user_id=owner_id, client_id=client_id, **deal_fields
    )

    repo = AsyncMock()
    repo.get_by_id.return_value = deal_model
    # Service tra phiếu theo DEAL (`get_intake_for_deal`), không theo client. Chỉ mock
    # `get_intake_by_client_id` thì `intake` chỉ là MagicMock tự sinh, và mọi assert về nội
    # dung prompt đều vô nghĩa vì f-string in ra "<MagicMock id=...>".  #Huynh
    repo.get_intake_for_deal.return_value = intake
    repo.get_intake_by_client_id.return_value = intake
    repo.list_attachments_with_text.return_value = attachments or []
    repo.create_lead_score.return_value = None
    repo.save.return_value = deal_model

    ai_facade = AsyncMock()
    ai_facade.qualify_lead.return_value = ai_result
    # last_usage() là hàm ĐỒNG BỘ. Để AsyncMock thì nó trả coroutine không ai await,
    # pytest báo lỗi (filterwarnings = error).
    ai_facade.last_usage = MagicMock(return_value=None)

    service = DealsService(db=AsyncMock(), repo=repo, ai_facade=ai_facade, usage=AsyncMock())
    return service, intake, deal_model


async def test_qualify_deal_writes_all_signal_fields_to_deal() -> None:
    service, _, deal_model = _make_qualify_service(_AI_RESULT)

    await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_reasoning == "Strong budget and clear timeline."
    assert deal_model.ai_qualification_project_type == "E-commerce website"
    assert deal_model.ai_qualification_budget_signal == "HIGH"
    assert deal_model.ai_qualification_timeline_signal == "CLEAR"
    assert deal_model.ai_qualification_urgency_signal == "MODERATE"
    assert deal_model.ai_qualification_red_flags == ["no mockups provided"]
    assert deal_model.ai_qualification_next_step == "Reply today to confirm scope and move to quoting."
    assert deal_model.ai_qualification_suggested_actions == [
        "Reply today to confirm scope",
        "Generate AI quote after scope confirmation",
        "Set follow-up reminder in 24 hours",
    ]
    assert deal_model.ai_qualification_price_range_min == 10000000
    assert deal_model.ai_qualification_price_range_max == 25000000
    assert len(deal_model.ai_qualification_detected_signals) == 3
    assert deal_model.ai_qualification_detected_signals[0]["is_positive"] is True
    assert deal_model.ai_qualification_detected_signals[2]["is_positive"] is False


# Ba test dưới đây TRƯỚC ĐÂY khoá lại bảng tra {"HOT": 80, "WARM": 50, "COLD": 20} —
# tức là chúng đang bảo vệ đúng cái thứ khiến điểm số vô nghĩa: mọi deal WARM đều ra
# đúng 50/100 dù là deal 20 triệu hay deal 700 nghìn. Giờ điểm được cộng từ thang 5
# tiêu chí do AI chấm, và NHÃN suy ra TỪ điểm.  #Huynh


def _breakdown(scope: int, budget: int, timeline: int, detail: int, context: int) -> dict:
    return {
        "scope": {"points": scope, "reason": ""},
        "budget": {"points": budget, "reason": ""},
        "timeline": {"points": timeline, "reason": ""},
        "detail": {"points": detail, "reason": ""},
        "context": {"points": context, "reason": ""},
    }


async def test_qualify_deal_diem_cong_tu_thang_tieu_chi() -> None:
    service, _, deal_model = _make_qualify_service(
        {**_AI_RESULT, "score_breakdown": _breakdown(28, 25, 18, 13, 8)}
    )

    await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_score == 92  # 28+25+18+13+8
    assert deal_model.ai_qualification_recommendation == "qualify"


async def test_qualify_deal_nhan_suy_ra_tu_diem_chu_khong_tu_model() -> None:
    """Model bảo HOT nhưng điểm chỉ 30 → hệ thống phải nghe ĐIỂM, không nghe nhãn."""
    service, _, deal_model = _make_qualify_service(
        {
            **_AI_RESULT,
            "suggested_lead_score": "HOT",
            "score_breakdown": _breakdown(10, 10, 5, 3, 2),
        }
    )

    result = await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_score == 30
    assert result["suggested_lead_score"] == "COLD"
    assert deal_model.ai_qualification_recommendation == "pass"


async def test_qualify_deal_hai_deal_khac_nhau_ra_diem_khac_nhau() -> None:
    """Chính là thứ bảng tra cũ không làm được: deal nào cũng ra đúng 50."""
    service_a, _, deal_a = _make_qualify_service(
        {**_AI_RESULT, "score_breakdown": _breakdown(30, 25, 20, 15, 10)}
    )
    service_b, _, deal_b = _make_qualify_service(
        {**_AI_RESULT, "score_breakdown": _breakdown(5, 20, 0, 5, 0)}
    )

    await service_a.qualify_deal(deal_a.owner_user_id, deal_a.id)
    await service_b.qualify_deal(deal_b.owner_user_id, deal_b.id)

    assert deal_a.ai_qualification_score == 100
    assert deal_b.ai_qualification_score == 30
    assert deal_a.ai_qualification_score != deal_b.ai_qualification_score


async def test_qualify_deal_missing_ai_facade_raises() -> None:
    deal_model = DealModelStub(id=uuid.uuid4(), owner_user_id=uuid.uuid4(), client_id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_id.return_value = deal_model
    service = DealsService(db=AsyncMock(), repo=repo, ai_facade=None, usage=AsyncMock())

    with pytest.raises(RuntimeError, match="AIFacade not initialized"):
        await service.qualify_deal(deal_model.owner_user_id, deal_model.id)


async def test_qualify_deal_complete_ai_output_does_not_warn() -> None:
    service, _, deal_model = _make_qualify_service(_AI_RESULT)

    with structlog.testing.capture_logs() as logs:
        await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    warnings = [e for e in logs if e["event"] == "deals.qualify_deal.incomplete_ai_output"]
    assert warnings == []


async def test_qualify_deal_incomplete_ai_output_logs_missing_keys() -> None:
    incomplete_result = {
        k: v for k, v in _AI_RESULT.items() if k not in ("detected_signals", "price_range_min")
    }
    service, _, deal_model = _make_qualify_service(incomplete_result)

    with structlog.testing.capture_logs() as logs:
        await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    warnings = [e for e in logs if e["event"] == "deals.qualify_deal.incomplete_ai_output"]
    assert len(warnings) == 1
    assert warnings[0]["log_level"] == "warning"
    assert warnings[0]["deal_id"] == str(deal_model.id)
    assert warnings[0]["missing_keys"] == ["detected_signals", "price_range_min"]


# ---------------------------------------------------------------------------
# qualify_deal — ngữ cảnh gửi cho AI (thuần chuỗi, KHÔNG gọi LLM)
# ---------------------------------------------------------------------------


class TestInquiryContext:
    """Dán chữ vào ô "Nội dung yêu cầu" phải nằm CÙNG khối với brief khách gửi kèm.

    Bug thật, đo trên bản đang chạy: cùng một bản brief, gửi bằng file PDF thì chấm ngon,
    copy dán vào ô "Nội dung yêu cầu" thì chấm 12/100 — budget 0 dù có "Ngân sách: 700
    triệu", timeline 0 dù có "Thời gian build: 5 tháng". Chữ KHÔNG mất (deals.notes có 306
    ký tự trong DB), nó chỉ bị dán nhãn "Ghi chú nội bộ" dưới tiêu đề "không phải lời khách"
    — mà prompt ra luật không chấm khối đó.

    Trước đây KHÔNG có test nào chạm vào `inquiry_context`, nên một lỗi dán nhãn đi thẳng ra
    sản phẩm mà không ai chặn được.  #Huynh
    """

    @staticmethod
    async def _context(*, intake_text=None, attachments=None, **deal_fields) -> str:
        service, _, deal_model = _make_qualify_service(
            _AI_RESULT, intake_text=intake_text, attachments=attachments, **deal_fields
        )
        return await service._build_inquiry_context(deal_model, deal_model.owner_user_id)

    async def test_noi_dung_yeu_cau_nam_trong_khoi_cham_diem(self) -> None:
        ctx = await self._context(notes="Ngân sách: 700 triệu. Thời gian build: 5 tháng.")

        assert ctx.startswith(SCORED_BLOCK_HEADING)
        scored = ctx.partition(EXCLUDED_BLOCK_HEADING)[0]
        assert "- Nội dung yêu cầu: Ngân sách: 700 triệu. Thời gian build: 5 tháng." in scored

    async def test_khong_con_dan_nhan_ghi_chu_noi_bo(self) -> None:
        """Đúng hai chuỗi này làm AI bỏ qua chữ người dùng dán vào — cấm chúng quay lại."""
        ctx = await self._context(
            notes="5 hạng mục: đăng nhập, giỏ hàng, thanh toán, CMS, báo cáo"
        )

        assert "Ghi chú nội bộ" not in ctx
        assert "FREELANCER TỰ NHẬP" not in ctx
        assert "5 hạng mục" in ctx

    async def test_dan_chu_va_gui_file_ra_cung_mot_khoi(self) -> None:
        """Yêu cầu của người dùng: thích dùng đường nào cũng được, điểm phải như nhau."""
        brief = "Ngân sách: 700 triệu. Thời gian build: 5 tháng. Hạng mục: A, B, C, D, E."

        dan = await self._context(notes=brief)
        gui_file = await self._context(
            attachments=[AttachmentStub(filename="brief.pdf", extracted_text=brief)]
        )

        for ctx in (dan, gui_file):
            assert brief in ctx.partition(EXCLUDED_BLOCK_HEADING)[0]
            assert ctx.index(SCORED_BLOCK_HEADING) < ctx.index(brief)

    async def test_gia_tri_du_kien_chi_nam_trong_khoi_cam(self) -> None:
        """Hồi quy bug GỐC: "Estimated value: 200000 VND" từng bị chấm 20/25 ngân sách."""
        ctx = await self._context(notes="Khách chưa nói gì về tiền.", estimated_value=200000)

        scored, sep, excluded = ctx.partition(EXCLUDED_BLOCK_HEADING)
        assert sep == EXCLUDED_BLOCK_HEADING
        assert "200000" not in scored
        assert "Giá trị dự kiến" not in scored
        assert "200000" in excluded

    async def test_khong_co_gia_tri_du_kien_thi_khong_in_khoi_cam(self) -> None:
        """Tiêu đề rỗng chỉ tổ mời model đi tìm xem "khối kia" nằm ở đâu."""
        ctx = await self._context(notes="Làm web bán hàng")

        assert EXCLUDED_BLOCK_HEADING not in ctx

    async def test_nguon_deal_van_o_khoi_cham_diem(self) -> None:
        """Tiêu chí `context` cho điểm "kênh khách đến" — đẩy `source` sang khối cấm là tự trừ."""
        ctx = await self._context(source="referral", estimated_value=200000)

        assert "- Nguồn deal: referral" in ctx.partition(EXCLUDED_BLOCK_HEADING)[0]

    async def test_chi_co_ten_du_an_thi_khoi_cham_diem_chi_mot_dong(self) -> None:
        """Luật "chỉ có tên dự án -> scope tối đa 12" phải còn nhận ra được tình huống đó."""
        ctx = await self._context()

        assert ctx.splitlines() == [SCORED_BLOCK_HEADING, "- Tên dự án: Test Deal"]

    async def test_chuoi_ghep_duoc_truyen_thang_xuong_ai(self) -> None:
        """Khoá luôn phần đấu dây: dựng đúng mà gọi sai tham số thì cũng vô nghĩa."""
        service, _, deal_model = _make_qualify_service(
            _AI_RESULT, intake_text=None, notes="Ngân sách: 700 triệu"
        )

        await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

        sent = service.ai_facade.qualify_lead.await_args.kwargs["inquiry_text"]
        assert sent.startswith(SCORED_BLOCK_HEADING)
        assert "Ngân sách: 700 triệu" in sent

    async def test_tieu_de_khoi_khop_voi_prompt(self) -> None:
        """Mã nguồn và prompt phải gọi hai khối bằng ĐÚNG một tên.

        Đây là chỗ duy nhất phát hiện được việc sửa tiêu đề ở một phía: AI không báo lỗi khi
        luật trỏ vào một khối không tồn tại, nó chỉ lặng lẽ chấm sai.  #Huynh
        """
        prompt = load_prompt("lead_qualifier")

        assert SCORED_BLOCK_HEADING in prompt
        assert EXCLUDED_BLOCK_HEADING in prompt
