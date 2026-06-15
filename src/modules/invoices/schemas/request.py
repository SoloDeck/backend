import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class InvoiceLineItemRequest(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    sort_order: int = 0


class InvoiceRequest(BaseModel):
    client_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    issue_date: date | None = None
    subtotal: Decimal | None = None
    tax_rate: Decimal = Decimal("0")
    currency: str = "VND"
    due_date: date
    notes: str | None = None
    line_items: list[InvoiceLineItemRequest] | None = None


class InvoiceUpdateRequest(BaseModel):
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax_rate: Decimal | None = None
    notes: str | None = None
    line_items: list[InvoiceLineItemRequest] | None = None


class PaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_date: date
    payment_method: str = "other"
    reference_note: str | None = None
