import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

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
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(NotFoundError):
        await service.create(uuid.uuid4(), DealRequest(client_id=uuid.uuid4(), title="Deal"))


async def test_transition_rejects_backward_stage() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="in_negotiation")
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="proposal_sent")
        )


async def test_transition_rejects_unknown_stage_as_domain_error() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="new_lead")
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="not_a_stage")
        )


async def test_transition_to_active_requires_accepted_proposal() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="in_negotiation")
    repo.has_accepted_proposal.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active")
        )


async def test_transition_to_completed_requires_invoice() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="active")
    repo.has_invoice.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(
            uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="completed_and_billed")
        )


async def test_transition_from_terminal_stage_is_rejected() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="completed_and_billed")
    service = DealsService(db=AsyncMock(), repo=repo)

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
    service = DealsService(db=AsyncMock(), repo=repo)

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


async def test_create_public_intake_rejects_unknown_token() -> None:
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = None
    service = DealsService(db=AsyncMock(), repo=repo)

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

    service = DealsService(db=AsyncMock(), repo=repo, ai_facade=ai_facade)
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


async def test_qualify_deal_hot_score_maps_to_80_and_qualify() -> None:
    service, _, deal_model = _make_qualify_service(
        {**_AI_RESULT, "suggested_lead_score": "HOT"}
    )

    await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_score == 80
    assert deal_model.ai_qualification_recommendation == "qualify"


async def test_qualify_deal_cold_score_maps_to_20_and_pass() -> None:
    service, _, deal_model = _make_qualify_service(
        {**_AI_RESULT, "suggested_lead_score": "COLD"}
    )

    await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_score == 20
    assert deal_model.ai_qualification_recommendation == "pass"


async def test_qualify_deal_warm_score_maps_to_50() -> None:
    service, _, deal_model = _make_qualify_service(
        {**_AI_RESULT, "suggested_lead_score": "WARM"}
    )

    await service.qualify_deal(deal_model.owner_user_id, deal_model.id)

    assert deal_model.ai_qualification_score == 50


async def test_qualify_deal_missing_ai_facade_raises() -> None:
    deal_model = DealModelStub(id=uuid.uuid4(), owner_user_id=uuid.uuid4(), client_id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_id.return_value = deal_model
    service = DealsService(db=AsyncMock(), repo=repo, ai_facade=None)

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
