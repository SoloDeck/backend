import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    contract_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    invoice_number: str
    status: str
    issue_date: date
    due_date: date
    currency: str
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal
    notes: str | None
    share_token: str | None = None
    created_at: datetime
    updated_at: datetime


class PaymentRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    payment_date: date
    payment_method: str
    reference_note: str | None
    created_at: datetime
