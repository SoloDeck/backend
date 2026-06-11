import uuid
from dataclasses import dataclass

from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money


@dataclass(frozen=True)
class ContractCreatedEvent(DomainEvent):
    deal_id: uuid.UUID
    proposal_id: uuid.UUID
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class ContractSignedEvent(DomainEvent):
    deal_id: uuid.UUID
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class ContractMilestoneReachedEvent(DomainEvent):
    """Consumed by Invoices to trigger automatic invoice creation."""
    milestone_id: uuid.UUID
    deal_id: uuid.UUID
    amount: Money


@dataclass(frozen=True)
class ContractCompletedEvent(DomainEvent):
    deal_id: uuid.UUID


@dataclass(frozen=True)
class ContractTerminatedEvent(DomainEvent):
    deal_id: uuid.UUID
    reason: str | None
