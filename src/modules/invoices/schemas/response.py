import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PaymentReminderInfo(BaseModel):
    """Lời nhắc thanh toán vừa được đặt (hoặc vì sao không đặt) — để web nói đúng cho người dùng."""

    scheduled: bool
    scheduled_at: datetime | None = None
    # Quy tắc "tới hạn" đang nhắc trước hạn mấy ngày; có cả khi không đặt được (để giải thích).
    days_before_due: int | None = None
    # Lời nhắc do quy tắc tạo luôn chờ freelancer duyệt trước khi gửi cho khách.
    requires_approval: bool = False
    # Không đặt được thì vì sao: disabled | too_soon | no_client_email | error.
    reason: str | None = None


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
    # Kết quả việc tự đặt lời nhắc thanh toán khi GỬI hóa đơn này (`reminders.invoice_reminders`).
    # Chỉ có trong phản hồi của lệnh gửi có xin đặt lời nhắc; mọi nơi khác là `None`.
    payment_reminder: PaymentReminderInfo | None = None
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
