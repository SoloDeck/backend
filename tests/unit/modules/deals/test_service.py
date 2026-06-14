import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import DealRequest, DealStageRequest
from src.shared.exceptions.domain import BusinessRuleError, InvalidStateTransitionError, NotFoundError


@dataclass
class DealStub:
    id: uuid.UUID
    stage: str
    closed_at: object | None = None


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
