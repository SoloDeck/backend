import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="after")
    def _due_date_not_before_issue_date(self) -> "InvoiceRequest":
        """Hạn thanh toán không được TRƯỚC ngày xuất hoá đơn.

        Trước đây tạo được hoá đơn xuất hôm nay mà hạn trả là 10 ngày TRƯỚC — API trả 201.
        Hoá đơn đó sinh ra đã quá hạn, và hệ thống nhắc nợ sẽ đòi tiền khách ngay lập tức
        vì một lỗi nhập liệu.  #Huynh
        """
        if self.issue_date and self.due_date < self.issue_date:
            raise ValueError("due_date cannot be earlier than issue_date")
        return self


class InvoiceUpdateRequest(BaseModel):
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax_rate: Decimal | None = None
    notes: str | None = None
    line_items: list[InvoiceLineItemRequest] | None = None


class InvoiceSendRequest(BaseModel):
    """Tuỳ chọn khi gửi hóa đơn. Body để trống thì gửi email kèm QR tự sinh."""

    # `False` = CHỈ đánh dấu đã gửi, không gửi thư. Dành cho freelancer đã tự gửi tay qua
    # Zalo/Messenger — trước đây đây là hành vi DUY NHẤT của endpoint này, nên giữ lại một
    # đường đi cho nó thay vì bắt mọi người phải gửi email.  #Huynh
    notify: bool = True
    # Ảnh freelancer tự đính (ảnh mã QR chụp từ app ngân hàng, ảnh sản phẩm…). Mỗi phần tử
    # là `{"key", "filename", "content_type"}` do `POST /reminders/attachments` trả về —
    # dùng lại đúng kho ảnh đó, không dựng đường tải lên thứ hai.
    #
    # Có ảnh thì thư KHÔNG kèm QR tự sinh nữa (xem `build_payment_block(with_qr=…)`).
    attachments: list[dict[str, str]] = Field(default_factory=list)


class PaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_date: date
    payment_method: str = "other"
    reference_note: str | None = None
