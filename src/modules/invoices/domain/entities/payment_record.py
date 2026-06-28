import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.shared.domain.value_objects.money import Money


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    MOMO = "momo"
    CASH = "cash"
    ONLINE = "online"
    OTHER = "other"


@dataclass(frozen=True)
class PaymentRecord:
    """Append-only record of a single payment received against an invoice."""

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Money
    method: PaymentMethod
    reference: str | None  # bank ref, MoMo transaction ID, etc.
    note: str | None
    recorded_at: datetime
