import uuid
from dataclasses import dataclass

from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class ProposalCreatedEvent(DomainEvent):
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID
    version: int
    ai_generated: bool


@dataclass(frozen=True)
class ProposalSentEvent(DomainEvent):
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class ProposalAcceptedEvent(DomainEvent):
    """Consumed by Deals to advance the deal stage to Active."""

    deal_id: uuid.UUID
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class ProposalRejectedEvent(DomainEvent):
    deal_id: uuid.UUID
    reason: str | None


@dataclass(frozen=True)
class ProposalExpiredEvent(DomainEvent):
    deal_id: uuid.UUID
