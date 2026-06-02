import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money
from src.modules.proposals.domain.entities.proposal import Proposal
from src.modules.proposals.domain.value_objects.proposal_status import ProposalStatus
from src.modules.proposals.domain.events.proposal_events import (
    ProposalCreatedEvent,
    ProposalSentEvent,
    ProposalAcceptedEvent,
    ProposalRejectedEvent,
    ProposalExpiredEvent,
)


@dataclass
class ProposalAggregate:
    proposal: Proposal
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def create(
        cls,
        deal_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        title: str,
        content: dict[str, object],
        total_value: Money,
        valid_until: datetime | None = None,
        ai_generated: bool = False,
        previous_version: int = 0,
    ) -> "ProposalAggregate":
        now = datetime.now(timezone.utc)
        proposal_id = uuid.uuid4()
        version = previous_version + 1
        proposal = Proposal(
            id=proposal_id,
            deal_id=deal_id,
            owner_user_id=owner_user_id,
            version=version,
            status=ProposalStatus.DRAFT,
            title=title,
            content=content,
            total_value=total_value,
            valid_until=valid_until,
            share_token=None,
            share_token_expires_at=None,
            ai_generated=ai_generated,
            sent_at=None,
            accepted_at=None,
            rejected_at=None,
            rejection_reason=None,
            created_at=now,
            updated_at=now,
        )
        agg = cls(proposal=proposal)
        agg._pending_events.append(
            ProposalCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=proposal_id,
                occurred_at=now,
                deal_id=deal_id,
                owner_user_id=owner_user_id,
                version=version,
                ai_generated=ai_generated,
            )
        )
        return agg

    def send(self) -> None:
        self.proposal.send()
        self._pending_events.append(
            ProposalSentEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.proposal.id,
                occurred_at=self.proposal.sent_at,  # type: ignore[arg-type]
                deal_id=self.proposal.deal_id,
                owner_user_id=self.proposal.owner_user_id,
            )
        )

    def accept(self) -> None:
        self.proposal.accept()
        self._pending_events.append(
            ProposalAcceptedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.proposal.id,
                occurred_at=self.proposal.accepted_at,  # type: ignore[arg-type]
                deal_id=self.proposal.deal_id,
                owner_user_id=self.proposal.owner_user_id,
            )
        )

    def reject(self, reason: str | None = None) -> None:
        self.proposal.reject(reason)
        self._pending_events.append(
            ProposalRejectedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.proposal.id,
                occurred_at=self.proposal.rejected_at,  # type: ignore[arg-type]
                deal_id=self.proposal.deal_id,
                reason=reason,
            )
        )

    def expire(self) -> None:
        self.proposal.expire()
        self._pending_events.append(
            ProposalExpiredEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.proposal.id,
                occurred_at=self.proposal.updated_at,
                deal_id=self.proposal.deal_id,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
