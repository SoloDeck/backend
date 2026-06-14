import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.shared.exceptions.domain import BusinessRuleError, InvalidStateTransitionError, NotFoundError


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
        await service.transition_stage(uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="proposal_sent"))


async def test_transition_rejects_unknown_stage_as_domain_error() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="new_lead")
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="not_a_stage"))


async def test_transition_to_active_requires_accepted_proposal() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="in_negotiation")
    repo.has_accepted_proposal.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active"))


async def test_transition_to_completed_requires_invoice() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="active")
    repo.has_invoice.return_value = False
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(BusinessRuleError):
        await service.transition_stage(uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="completed_and_billed"))


async def test_transition_from_terminal_stage_is_rejected() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = DealStub(id=uuid.uuid4(), stage="completed_and_billed")
    service = DealsService(db=AsyncMock(), repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await service.transition_stage(uuid.uuid4(), uuid.uuid4(), DealStageRequest(target_stage="active"))


def _intake_payload(**overrides) -> PublicIntakeRequest:
    data = {"name": "Lead Person", "inquiry_text": "I need a landing page."}
    data.update(overrides)
    return PublicIntakeRequest(**data)


async def test_create_public_intake_creates_client_deal_and_intake() -> None:
    owner = OwnerStub(id=uuid.uuid4())
    client_id = uuid.uuid4()
    intake = object()
    repo = AsyncMock()
    repo.get_owner_by_intake_token.return_value = owner
    repo.create_client.return_value = DealStub(id=client_id, stage="prospect")
    repo.create.return_value = DealStub(id=uuid.uuid4(), stage="new_lead")
    repo.create_intake.return_value = intake
    service = DealsService(db=AsyncMock(), repo=repo)

    # Unique token per test run so the shared process limiter is never the cause of failure.
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
