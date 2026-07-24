import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from src.shared.exceptions.domain import InvalidStateTransitionError


class PaymentProvider(StrEnum):
    MOMO = "momo"


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
        if self.status not in {SubscriptionPaymentStatus.PENDING, SubscriptionPaymentStatus.PROCESSING}:
            raise InvalidStateTransitionError(
                "SubscriptionPayment", self.status.value, SubscriptionPaymentStatus.CANCELLED.value
            )
        self.status = SubscriptionPaymentStatus.CANCELLED
        self.updated_at = datetime.now(UTC)
