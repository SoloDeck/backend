"""Unit tests for ProposalsService.transition_status."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.proposals.application.service import ProposalsService
from src.shared.exceptions.domain import InvalidStateTransitionError, NotFoundError


def _make_proposal(**kwargs) -> MagicMock:
    m = MagicMock()
    m.id = kwargs.get("id", uuid.uuid4())
    m.deal_id = kwargs.get("deal_id", uuid.uuid4())
    m.owner_user_id = kwargs.get("owner_user_id", uuid.uuid4())
    m.status = kwargs.get("status", "draft")
    m.sent_at = kwargs.get("sent_at")
    m.responded_at = kwargs.get("responded_at")
    return m


class TestTransitionStatus:
    async def test_draft_to_sent_succeeds(self) -> None:
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.side_effect = [proposal, None]  # _get_proposal, then no existing sent

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

        assert result.status == "sent"
        assert result.sent_at is not None
        mock_bus.publish.assert_awaited_once()
        call_args = mock_bus.publish.call_args[0]
        assert call_args[0] == "proposals.proposal_sent"

    async def test_draft_to_sent_supersedes_existing_sent(self) -> None:
        deal_id = uuid.uuid4()
        proposal = _make_proposal(status="draft", deal_id=deal_id)
        existing_sent = _make_proposal(status="sent", deal_id=deal_id)
        db = AsyncMock()
        db.scalar.side_effect = [proposal, existing_sent]

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

        assert existing_sent.status == "superseded"

    async def test_sent_to_accepted_sets_responded_at(self) -> None:
        proposal = _make_proposal(status="sent")
        db = AsyncMock()
        db.scalar.return_value = proposal

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "accepted")

        assert result.status == "accepted"
        assert result.responded_at is not None
        call_args = mock_bus.publish.call_args[0]
        assert call_args[0] == "proposals.proposal_accepted"

    async def test_sent_to_rejected_sets_responded_at(self) -> None:
        proposal = _make_proposal(status="sent")
        db = AsyncMock()
        db.scalar.return_value = proposal

        with patch("src.modules.proposals.application.service.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            svc = ProposalsService(db=db)
            result = await svc.transition_status(proposal.owner_user_id, proposal.id, "rejected")

        assert result.status == "rejected"
        assert result.responded_at is not None

    async def test_invalid_transition_raises(self) -> None:
        proposal = _make_proposal(status="draft")
        db = AsyncMock()
        db.scalar.return_value = proposal

        svc = ProposalsService(db=db)
        with pytest.raises(InvalidStateTransitionError):
            await svc.transition_status(proposal.owner_user_id, proposal.id, "accepted")

    async def test_terminal_status_raises(self) -> None:
        proposal = _make_proposal(status="accepted")
        db = AsyncMock()
        db.scalar.return_value = proposal

        svc = ProposalsService(db=db)
        with pytest.raises(InvalidStateTransitionError):
            await svc.transition_status(proposal.owner_user_id, proposal.id, "sent")

    async def test_not_found_raises(self) -> None:
        db = AsyncMock()
        db.scalar.return_value = None

        svc = ProposalsService(db=db)
        with pytest.raises(NotFoundError):
            await svc.transition_status(uuid.uuid4(), uuid.uuid4(), "sent")
