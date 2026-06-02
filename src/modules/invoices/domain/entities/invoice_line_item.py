import uuid
from dataclasses import dataclass
from decimal import Decimal

from src.shared.domain.value_objects.money import Money


@dataclass
class InvoiceLineItem:
    id: uuid.UUID
    invoice_id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Money
    sort_order: int

    def __post_init__(self) -> None:
        if self.quantity <= Decimal(0):
            raise ValueError("Line item quantity must be positive")
        if not self.description.strip():
            raise ValueError("Line item description must not be blank")

    @property
    def line_total(self) -> Money:
        return Money(self.unit_price.amount * self.quantity, self.unit_price.currency)
