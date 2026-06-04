import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class InvoiceRequest(BaseModel):
    client_id: uuid.UUID
    deal_id: uuid.UUID | None = None
    subtotal: Decimal
    tax_rate: Decimal = Decimal("0")
    currency: str = "VND"
    due_date: date
    notes: str | None = None
