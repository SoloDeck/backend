"""Unit tests for ContractsService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.schemas.request import ContractRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    InvalidStateTransitionError,
    NotFoundError,
)


def _make_contract(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.deal_id = kwargs.get("deal_id", uuid.uuid4())
    m.proposal_id = kwargs.get("proposal_id", uuid.uuid4())
    m.client_id = kwargs.get("client_id", uuid.uuid4())
    m.owner_user_id = kwargs.get("owner_user_id", uuid.uuid4())
    m.status = kwargs.get("status", "draft")
    m.signed_by_freelancer_at = None
    return m


def _make_proposal(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.status = kwargs.get("status", "accepted")
    return m


def _make_plan(**kwargs) -> MagicMock:
    m = MagicMock()
    m.can_export_pdf = kwargs.get("can_export_pdf", True)
    return m


def _make_sub(**kwargs) -> MagicMock:
    m = MagicMock()
    m.plan_id = kwargs.get("plan_id", uuid.uuid4())
    return m


def _make_payload(**kwargs) -> ContractRequest:
    return ContractRequest(
        deal_id=kwargs.get("deal_id", uuid.uuid4()),
        proposal_id=kwargs.get("proposal_id", uuid.uuid4()),
        client_id=kwargs.get("client_id", uuid.uuid4()),
        content=kwargs.get("content", {}),
    )


class TestCreate:
    async def test_raises_if_proposal_not_found(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError, match="Proposal"):
            await ContractsService(db=db).create(uuid.uuid4(), _make_payload())

    async def test_raises_if_proposal_not_accepted(self) -> None:
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.return_value = proposal

        with pytest.raises(BusinessRuleError, match="accepted proposal"):
            await ContractsService(db=db).create(uuid.uuid4(), _make_payload())

    async def test_creates_from_accepted_proposal(self) -> None:
        proposal = _make_proposal(status="accepted")
        client = MagicMock(id=uuid.uuid4(), name="Acme", email="a@b.com", phone=None)
        db = AsyncMock()
        db.scalar.side_effect = [proposal, 0, client]

        await ContractsService(db=db).create(uuid.uuid4(), _make_payload())

        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestTransitionStatus:
    async def test_draft_to_pending_signatures(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        result = await ContractsService(db=db).transition_status(
            contract.owner_user_id, contract.id, "pending_signatures"
        )
        assert result.status == "pending_signatures"

    async def test_pending_to_active_sets_signed_at(self) -> None:
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract

        result = await ContractsService(db=db).transition_status(
            contract.owner_user_id, contract.id, "active"
        )
        assert result.status == "active"
        assert result.signed_by_freelancer_at is not None

    async def test_invalid_transition_raises(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(InvalidStateTransitionError):
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "completed"
            )

    async def test_unknown_status_raises_business_rule(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="not a valid contract status"):
            await ContractsService(db=db).transition_status(
                contract.owner_user_id, contract.id, "bogus"
            )

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).transition_status(
                uuid.uuid4(), uuid.uuid4(), "pending_signatures"
            )


class TestExportPdf:
    async def test_raises_without_subscription(self) -> None:
        contract = _make_contract()
        db = AsyncMock()
        db.scalar.side_effect = [contract, None]

        with pytest.raises(EntitlementError):
            await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

    async def test_raises_when_plan_disallows_pdf(self) -> None:
        contract = _make_contract()
        sub = _make_sub()
        plan = _make_plan(can_export_pdf=False)
        db = AsyncMock()
        db.scalar.side_effect = [contract, sub, plan]

        with pytest.raises(EntitlementError, match="PDF export"):
            await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

    async def test_queues_task_and_returns_pending(self) -> None:
        contract = _make_contract()
        sub = _make_sub()
        plan = _make_plan(can_export_pdf=True)
        db = AsyncMock()
        db.scalar.side_effect = [contract, sub, plan]

        mock_task = MagicMock(id="celery-task-id-123")
        with patch("src.modules.contracts.application.service.render_contract_pdf") as mock_fn:
            mock_fn.delay.return_value = mock_task
            result = await ContractsService(db=db).export_pdf(contract.owner_user_id, contract.id)

        assert result["status"] == "pending"
        assert result["task_id"] == "celery-task-id-123"
        mock_fn.delay.assert_called_once_with(str(contract.id))

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).export_pdf(uuid.uuid4(), uuid.uuid4())


class TestDelete:
    async def test_deletes_draft(self) -> None:
        contract = _make_contract(status="draft")
        db = AsyncMock()
        db.scalar.return_value = contract

        await ContractsService(db=db).delete(contract.owner_user_id, contract.id)
        db.delete.assert_awaited_once_with(contract)

    async def test_deletes_expired(self) -> None:
        contract = _make_contract(status="expired")
        db = AsyncMock()
        db.scalar.return_value = contract

        await ContractsService(db=db).delete(contract.owner_user_id, contract.id)
        db.delete.assert_awaited_once_with(contract)

    async def test_raises_for_active_contract(self) -> None:
        contract = _make_contract(status="active")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="draft or expired"):
            await ContractsService(db=db).delete(contract.owner_user_id, contract.id)

    async def test_raises_for_pending_signatures(self) -> None:
        contract = _make_contract(status="pending_signatures")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError):
            await ContractsService(db=db).delete(contract.owner_user_id, contract.id)

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        with pytest.raises(NotFoundError):
            await ContractsService(db=db).delete(uuid.uuid4(), uuid.uuid4())


class TestUpdate:
    async def test_raises_when_not_draft(self) -> None:
        contract = _make_contract(status="active")
        db = AsyncMock()
        db.scalar.return_value = contract

        with pytest.raises(BusinessRuleError, match="draft status"):
            await ContractsService(db=db).update(
                contract.owner_user_id, contract.id, _make_payload()
            )
