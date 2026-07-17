import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)


@dataclass
class DealStub:
    id: uuid.UUID
    stage: str
    closed_at: object | None = None


@dataclass
class OwnerStub:
    id: uuid.UUID
    currency: str = "VND"


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


async def test_transition_to_completed_requires_invoice() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="active")
    repo.has_invoice.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="completed_and_billed")
        )


async def test_transition_from_terminal_stage_is_rejected() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="completed_and_billed")
    service = DealsService(db=AsyncMock(), repo=repo, usage=AsyncMock())

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active")
        )


def _intake_payload(**overrides) -> PublicIntakeRequest:
    data = {"name": "Lead Person", "inquiry_text": "I need a landing page."}
    data.update(overrides)
    return PublicIntakeRequest(**data)


async def test_create_public_intake_creates_client_deal_and_intake() -> None:
    owner = OwnerStub(id=uuid.uuid4())
    client_id = uuid.uuid4()
    intake = IntakeStub(id=uuid.uuid4(), client_id=client_id)
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = owner
    repo.create_client.return_value = DealStub(id=client_id, stage="prospect")
    repo.create.return_value = DealStub(id=uuid.uuid4(), stage="new_lead")
    repo.create_intake.return_value = intake

    # `Session.add()` là hàm ĐỒNG BỘ. Để AsyncMock tự sinh thì nó trả về một coroutine
    # không ai await → RuntimeWarning "coroutine was never awaited" và test đỏ vì một lý do
    # chẳng liên quan gì tới thứ đang được kiểm tra.  #Huynh
    db = AsyncMock()
    db.add = MagicMock()
    service = DealsService(db=db, repo=repo, usage=AsyncMock())

    # Unique token per test run so the shared process limiter is never the cause of failure.
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay", lambda *a: None)
        result = await service.create_public_intake(f"tok-{uuid.uuid4().hex}", _intake_payload())

    assert result is intake
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


def _make_qualify_service(ai_result: dict):
    client_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    intake = IntakeStub(id=uuid.uuid4(), client_id=client_id)
    deal_model = DealModelStub(id=deal_id, owner_user_id=owner_id, client_id=client_id)

    repo = AsyncMock()
    repo.get_by_id.return_value = deal_model
    repo.get_intake_by_client_id.return_value = intake
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
