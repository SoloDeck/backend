"""Subscriptions application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.subscriptions.application.payment_gateway import PaymentGateway
from src.modules.subscriptions.domain.entities.subscription_payment import (
    PaymentProvider,
    SubscriptionPayment,
    SubscriptionPaymentStatus,
)
from src.modules.subscriptions.domain.exceptions.exceptions import (
    InvalidPaymentSignatureError,
    PlanNotPurchasableError,
)
from src.modules.subscriptions.infrastructure.repository import SubscriptionsRepository
from src.modules.subscriptions.schemas.response import SubscriptionResponse
from src.shared.exceptions.domain import NotFoundError

_CHECKOUT_TTL_MINUTES = 15
_BILLING_PERIOD_DAYS = 30
# The provider's real server would call this notify_url — meaningless for the
# mock (nothing calls it), kept realistic for parity with a real integration.
_NOTIFY_URL = "https://api.solodesk.space/api/v1/payments/webhooks/momo"


def _payment_to_entity(row) -> SubscriptionPayment:
    return SubscriptionPayment(
        id=row.id,
        user_id=row.user_id,
        subscription_id=row.subscription_id,
        plan_id=row.plan_id,
        provider=PaymentProvider(row.provider),
        status=SubscriptionPaymentStatus(row.status),
        amount=row.amount,
        currency=row.currency,
        pay_url=row.pay_url,
        deeplink=row.deeplink,
        qr_code_url=row.qr_code_url,
        provider_reference=row.provider_reference,
        failure_reason=row.failure_reason,
        expires_at=row.expires_at,
        paid_at=row.paid_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@dataclass
class SubscriptionsService:
    db: AsyncSession
    repo: SubscriptionsRepository | None = None
    momo_client: PaymentGateway | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = SubscriptionsRepository(self.db)

    def _gateway(self, provider: PaymentProvider) -> PaymentGateway:
        if provider != PaymentProvider.MOMO or self.momo_client is None:
            raise RuntimeError(f"No payment gateway configured for provider '{provider}'")
        return self.momo_client

    async def list_plans(self) -> list:
        return await self.repo.list_active_plans()

    async def initiate_checkout(
        self, user_id: uuid.UUID, plan_id: uuid.UUID, provider: PaymentProvider
    ):
        subscription = await self.repo.get_subscription(user_id)
        if subscription is None:
            raise NotFoundError("No subscription found")

        plan = await self.repo.get_plan(plan_id)
        if plan is None or not plan.is_active:
            raise NotFoundError("Plan not found")
        if plan.price_monthly <= 0:
            raise PlanNotPurchasableError("The free plan does not require checkout")

        payment = await self.repo.create_payment(
            user_id=user_id,
            subscription_id=subscription.id,
            plan_id=plan.id,
            provider=provider.value,
            status=SubscriptionPaymentStatus.PENDING.value,
            amount=plan.price_monthly,
            currency=plan.currency,
            expires_at=datetime.now(UTC) + timedelta(minutes=_CHECKOUT_TTL_MINUTES),
        )

        gateway = self._gateway(provider)
        result = await gateway.create_payment(
            order_id=str(payment.id),
            amount=plan.price_monthly,
            currency=plan.currency,
            order_info=f"SoloDesk {plan.name} plan upgrade",
            notify_url=_NOTIFY_URL,
        )
        payment.pay_url = result.pay_url
        payment.deeplink = result.deeplink
        payment.qr_code_url = result.qr_code_url
        payment.raw_create_response = result.raw
        return await self.repo.save(payment)

    async def get_checkout_status(self, user_id: uuid.UUID, payment_id: uuid.UUID):
        payment = await self.repo.get_payment_by_id(payment_id)
        if payment is None or payment.user_id != user_id:
            raise NotFoundError("Payment intent not found")
        return payment

    async def cancel_checkout(self, user_id: uuid.UUID, payment_id: uuid.UUID):
        payment = await self.repo.get_payment_by_id(payment_id)
        if payment is None or payment.user_id != user_id:
            raise NotFoundError("Payment intent not found")

        entity = _payment_to_entity(payment)
        entity.cancel()  # raises InvalidStateTransitionError (-> 409) if not pending/processing
        payment.status = entity.status.value
        payment.updated_at = entity.updated_at
        return await self.repo.save(payment)

    async def handle_payment_callback(self, provider: PaymentProvider, raw_payload: dict) -> dict:
        gateway = self._gateway(provider)
        if not gateway.verify_callback_signature(raw_payload):
            raise InvalidPaymentSignatureError()
        parsed = gateway.parse_callback(raw_payload)

        try:
            payment_id = uuid.UUID(parsed.order_id)
        except ValueError as exc:
            raise NotFoundError(f"Unknown order '{parsed.order_id}'") from exc

        payment = await self.repo.get_payment_by_id(payment_id)
        if payment is None:
            raise NotFoundError(f"Unknown order '{parsed.order_id}'")

        if payment.status != SubscriptionPaymentStatus.PENDING:
            # Idempotent replay — providers retry callbacks until acked.
            return gateway.build_ack_response(parsed)

        now = datetime.now(UTC)
        if parsed.success:
            plan = await self.repo.get_plan(payment.plan_id)
            subscription = await self.repo.get_subscription(payment.user_id)

            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=_BILLING_PERIOD_DAYS)
            await self.repo.save(subscription)

            payment.status = SubscriptionPaymentStatus.SUCCEEDED.value
            payment.provider_reference = parsed.provider_reference
            payment.paid_at = now
            payment.raw_callback_payload = raw_payload
            await self.repo.save(payment)

            await self.repo.create_billing_event(
                user_id=payment.user_id,
                subscription_id=subscription.id,
                event_type="payment_succeeded",
                amount=payment.amount,
                currency=payment.currency,
                event_metadata={
                    "provider": provider.value,
                    "payment_id": str(payment.id),
                    "provider_reference": parsed.provider_reference,
                    "raw_callback": raw_payload,
                },
            )
        else:
            payment.status = SubscriptionPaymentStatus.FAILED.value
            payment.failure_reason = parsed.message
            payment.raw_callback_payload = raw_payload
            await self.repo.save(payment)

            await self.repo.create_billing_event(
                user_id=payment.user_id,
                subscription_id=payment.subscription_id,
                event_type="payment_failed",
                amount=payment.amount,
                currency=payment.currency,
                event_metadata={
                    "provider": provider.value,
                    "payment_id": str(payment.id),
                    "raw_callback": raw_payload,
                },
            )

        return gateway.build_ack_response(parsed)

    async def get_my_subscription(self, user_id: uuid.UUID) -> SubscriptionResponse:
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No active subscription found")

        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None:
            raise NotFoundError("Subscription plan not found")

        return SubscriptionResponse(
            id=sub.id,
            user_id=sub.user_id,
            plan_id=sub.plan_id,
            plan_name=plan.name,
            plan_slug=plan.slug,
            status=sub.status,
            current_period_start=sub.current_period_start,
            current_period_end=sub.current_period_end,
            cancel_at_period_end=sub.cancel_at_period_end,
        )
