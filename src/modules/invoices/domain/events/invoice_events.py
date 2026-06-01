import uuid
from dataclasses import dataclass

from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money


@dataclass(frozen=True)
class InvoiceCreatedEvent(DomainEvent):
    deal_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class InvoiceSentEvent(DomainEvent):
    owner_user_id: uuid.UUID
    total: Money


@dataclass(frozen=True)
class PaymentRecordedEvent(DomainEvent):
    amount_paid: Money
    remaining: Money


@dataclass(frozen=True)
class InvoicePaidEvent(DomainEvent):
    """Consumed by Deals — may trigger completed_and_billed stage."""
    deal_id: uuid.UUID | None
    owner_user_id: uuid.UUID


@dataclass(frozen=True)
class InvoiceOverdueEvent(DomainEvent):
    deal_id: uuid.UUID | None
    owner_user_id: uuid.UUID
