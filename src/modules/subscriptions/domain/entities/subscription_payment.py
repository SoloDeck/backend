import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from src.shared.exceptions.domain import InvalidStateTransitionError

ORDER_CODE_PREFIX = "SD"
ORDER_CODE_BODY_LENGTH = 8

# Bảng chữ Crockford base32: bỏ I, L, O, U.
#
# Bỏ I/L/O vì chúng lẫn với 1/1/0 — mã này sẽ được ĐỌC TỪ MÀN HÌNH RỒI GÕ TAY vào ô nội
# dung chuyển khoản, nên mỗi cặp ký tự nhìn giống nhau là một khoản tiền vào mà không
# khớp được đơn nào. Bỏ U vì nó biến những chuỗi ngẫu nhiên vô hại thành từ tục tĩu.
_ORDER_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_order_code() -> str:
    """Mã đơn ngắn dạng ``SD7K2M9PQR`` — đủ ngắn để gõ vào nội dung chuyển khoản.

    Dùng `secrets` chứ không `random`: mã này lộ ra ngoài (nó nằm trong nội dung chuyển
    khoản, người khác nhìn thấy được), nên một bộ sinh đoán được cho phép dò ra mã của
    đơn khác.

    KHÔNG có vòng thử lại khi trùng. Không gian mã là 32^8 ≈ 1,1 nghìn tỷ, nên ở quy mô
    này trùng là chuyện không xảy ra — và nếu có, unique index chặn ngay lúc INSERT: lần
    checkout đó hỏng và người dùng bấm lại. Hỏng một lần rồi thử lại là kết cục ĐÚNG; cái
    phải tránh bằng mọi giá là hai đơn khác nhau mang cùng một mã, vì lúc đó một khoản
    tiền vào sẽ khớp nhầm đơn. Unique index lo đúng việc đó.
    """
    body = "".join(secrets.choice(_ORDER_CODE_ALPHABET) for _ in range(ORDER_CODE_BODY_LENGTH))
    return f"{ORDER_CODE_PREFIX}{body}"


class PaymentProvider(StrEnum):
    MOMO = "momo"
    ZALOPAY = "zalopay"
    SEPAY = "sepay"


class SubscriptionPaymentStatus(StrEnum):
    """Mirrors the `PaymentIntentStatus` enum in contracts/openapi.yaml."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class SubscriptionPayment:
    """A payment intent to upgrade a subscription to a paid plan.

    `id` doubles as the order code we hand to the payment provider (MoMo's
    `orderId`) — there is no separate order-id column to keep in sync.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    provider: PaymentProvider
    status: SubscriptionPaymentStatus
    amount: Decimal
    currency: str
    pay_url: str | None
    deeplink: str | None
    qr_code_url: str | None
    provider_reference: str | None
    failure_reason: str | None
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def mark_succeeded(self, provider_reference: str | None) -> None:
        if self.status != SubscriptionPaymentStatus.PENDING:
            raise InvalidStateTransitionError(
                "SubscriptionPayment", self.status.value, SubscriptionPaymentStatus.SUCCEEDED.value
            )
        self.status = SubscriptionPaymentStatus.SUCCEEDED
        self.provider_reference = provider_reference
        self.paid_at = datetime.now(UTC)
        self.updated_at = self.paid_at

    def mark_failed(self, reason: str) -> None:
        if self.status != SubscriptionPaymentStatus.PENDING:
            raise InvalidStateTransitionError(
                "SubscriptionPayment", self.status.value, SubscriptionPaymentStatus.FAILED.value
            )
        self.status = SubscriptionPaymentStatus.FAILED
        self.failure_reason = reason
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        if self.status not in {
            SubscriptionPaymentStatus.PENDING,
            SubscriptionPaymentStatus.PROCESSING,
        }:
            raise InvalidStateTransitionError(
                "SubscriptionPayment", self.status.value, SubscriptionPaymentStatus.CANCELLED.value
            )
        self.status = SubscriptionPaymentStatus.CANCELLED
        self.updated_at = datetime.now(UTC)
