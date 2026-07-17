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


class PaymentLinkResponse(BaseModel):
    type: Literal["checkout_url", "deep_link", "qr_code", "bank_transfer_instruction"]
    url: str | None = None
    qr_code_url: str | None = None
    instructions: str | None = None


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
            payment_link=PaymentLinkResponse(
                type="checkout_url",
                url=row.pay_url,
                qr_code_url=row.qr_code_url,
                instructions=row.deeplink,
            ),
            provider_reference=row.provider_reference,
            paid_at=row.paid_at,
            expires_at=row.expires_at,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
