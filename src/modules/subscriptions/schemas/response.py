import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    price_monthly: Decimal
    currency: str
    can_use_ai: bool
    can_export_pdf: bool
    max_clients: int | None
    max_deals: int | None
    max_ai_generations_per_month: int


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    plan_slug: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool


class UsageRecordResponse(BaseModel):
    user_id: uuid.UUID
    billing_period_start: datetime
    billing_period_end: datetime
    ai_generations_used: int
    ai_generations_limit: int


class PaymentLinkResponse(BaseModel):
    type: Literal["checkout_url", "deep_link", "qr_code", "bank_transfer_instruction"]
    url: str | None = None
    qr_code_url: str | None = None
    instructions: str | None = None


def _vnd(amount) -> str:
    """``199000`` → ``"199.000"`` — dấu chấm ngăn nghìn theo lối Việt."""
    return f"{int(amount):,}".replace(",", ".")


def _sepay_instructions(row) -> str | None:
    """Câu hướng dẫn chuyển khoản, đọc được bằng mắt, cho người dùng gõ tay.

    QUÉT QR HỎNG LÀ CHUYỆN THƯỜNG: thiếu sáng, app ngân hàng không quét được từ màn
    hình, người dùng đang ngồi trên máy tính. Lúc đó thứ duy nhất cứu được giao dịch là
    bốn con số đọc được: ngân hàng, số tài khoản, số tiền, và NỘI DUNG chuyển khoản.

    Trước bản này cả bốn thứ đó chỉ tồn tại bên trong query string của ảnh QR, nên phía
    client muốn hiện ra phải tự bóc URL — một ràng buộc ngầm giữa hai repo, không có gì
    bắt lỗi khi nó vỡ.

    Đọc từ `raw_create_response` (thứ adapter đã ghi lại) chứ không từ Settings: bản ghi
    cũ phải giữ nguyên số tài khoản LÚC ĐÓ, chứ không phải số tài khoản hiện tại.
    """
    raw = row.raw_create_response or {}
    account = raw.get("account_number")
    bank = raw.get("bank")
    code = row.order_code or raw.get("order_code")
    if not (account and bank and code):
        return None
    return (
        f"Chuyển khoản {_vnd(row.amount)}đ tới số tài khoản {account} ({bank}), "
        f"nội dung ghi đúng: {code}"
    )


def _payment_link(row) -> "PaymentLinkResponse":
    """`type` phải nói ĐÚNG bản chất của `url`, vì client dùng nó để quyết định làm gì.

    Bản trước hard-code `"checkout_url"` cho MỌI cổng. Với SePay thì `url` là một tấm
    ẢNH PNG chứ không phải trang thanh toán — client nào tin vào `type` (mà đó chính là
    việc của một trường phân loại) sẽ điều hướng trình duyệt thẳng vào file ảnh.

    `bank_transfer_instruction` đã nằm sẵn trong Literal của `PaymentLinkResponse` từ
    đầu và chưa cổng nào phát ra. Đây đúng là chỗ dùng nó: SePay không có gì để điều
    hướng tới, chỉ có thông tin để hiển thị và chờ tiền vào.
    """
    if row.provider == "sepay":
        return PaymentLinkResponse(
            type="bank_transfer_instruction",
            url=row.pay_url,
            qr_code_url=row.qr_code_url,
            instructions=_sepay_instructions(row),
        )
    return PaymentLinkResponse(
        type="checkout_url",
        url=row.pay_url,
        qr_code_url=row.qr_code_url,
        instructions=row.deeplink,
    )


class PaymentIntentResponse(BaseModel):
    """Matches contracts/openapi.yaml's PaymentIntentResponse, subscription-targeted
    (invoice_id omitted — invoice payment-links aren't implemented yet)."""

    id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    provider: str
    status: str
    amount: Decimal
    currency: str
    # Mã đơn ngắn (`SD7K2M9PQR`) — thứ người dùng gõ vào nội dung chuyển khoản.
    # `None` với bản ghi tạo trước khi cột này tồn tại, và với cổng không cần tới nó.
    order_code: str | None
    payment_link: PaymentLinkResponse
    provider_reference: str | None
    paid_at: datetime | None
    expires_at: datetime
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row) -> "PaymentIntentResponse":
        return cls(
            id=row.id,
            subscription_id=row.subscription_id,
            plan_id=row.plan_id,
            provider=row.provider,
            status=row.status,
            amount=row.amount,
            currency=row.currency,
            order_code=row.order_code,
            payment_link=_payment_link(row),
            provider_reference=row.provider_reference,
            paid_at=row.paid_at,
            expires_at=row.expires_at,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
