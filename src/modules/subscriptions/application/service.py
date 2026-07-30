"""Subscriptions application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.modules.subscriptions.application.payment_gateway import PaymentGateway
from src.modules.subscriptions.domain.entities.subscription_payment import (
    PaymentProvider,
    SubscriptionPayment,
    SubscriptionPaymentStatus,
)
from src.modules.subscriptions.domain.exceptions.exceptions import (
    InvalidPaymentSignatureError,
    PlanNotPurchasableError,
    SubscriptionNotCancellableError,
)
from src.modules.subscriptions.infrastructure.repository import SubscriptionsRepository
from src.modules.subscriptions.schemas.response import SubscriptionResponse
from src.shared.exceptions.domain import NotFoundError

log = structlog.get_logger(__name__)

# 15 phút quá chật cho một lần trả tiền thật: mở app MoMo, đăng nhập, nhập OTP, cộng độ trễ
# MoMo giao IPN. Hết hạn giữa chừng không làm mất tiền (xem `handle_payment_callback`), nhưng
# làm người dùng thấy "đã hết hạn" trong lúc họ vẫn đang trả — nên nới ra.  #Huynh
_CHECKOUT_TTL_MINUTES = 30
_BILLING_PERIOD_DAYS = 30
# Matches the "perpetual" free-plan period used at registration (AuthService).
_FREE_PLAN_PERIOD_DAYS = 36500


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
        self,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        provider: PaymentProvider,
        return_url: str | None = None,
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
            notify_url=settings.momo_ipn_url,
            redirect_url=return_url,
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
        return await self._expire_if_overdue(payment)

    async def _expire_if_overdue(self, payment):
        """Lazily flip a stale pending checkout to `expired` on read, rather
        than leaving it reporting `pending` forever with no job to sweep it."""
        if (
            payment.status == SubscriptionPaymentStatus.PENDING
            and payment.expires_at <= datetime.now(UTC)
        ):
            payment.status = SubscriptionPaymentStatus.EXPIRED.value
            payment.updated_at = datetime.now(UTC)
            payment = await self.repo.save(payment)
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

        log.info(
            "payments.callback_received",
            provider=provider.value,
            order_id=parsed.order_id,
            success=parsed.success,
        )

        # Row lock held until this request commits/rolls back — serializes
        # concurrent deliveries of the same callback so only one can pass the
        # PENDING check below.
        payment = await self.repo.get_payment_by_id_for_update(payment_id)
        if payment is None:
            raise NotFoundError(f"Unknown order '{parsed.order_id}'")

        # Cửa sổ thanh toán có thể đã trôi qua trước khi callback này tới.
        #
        # TRẢ TIỀN THÀNH CÔNG THÌ LUÔN KÍCH HOẠT, kể cả intent đã quá hạn: tiền là THẬT,
        # MoMo không báo thành công cho giao dịch không xảy ra. Bản trước gọi
        # `_expire_if_overdue` cho MỌI callback, nên một IPN thành công đến muộn bị đánh dấu
        # `expired` rồi rơi vào nhánh replay — hệ thống ack "Confirm Success" cho MoMo mà
        # KHÔNG kích hoạt gói. Người dùng mất tiền, không nhận được gì, và vì file này khi
        # đó không có một dòng log nào nên không ai biết chuyện đã xảy ra.
        #
        # Mối lo trong comment cũ ("đừng lặng lẽ kích hoạt cho intent đã bỏ") vẫn đúng —
        # nhưng cách xử đúng là làm cho nó ỒN ÀO, không phải chặn. Ta không có đường hoàn
        # tiền tự động, nên từ chối kích hoạt là lấy tiền mà không giao hàng.  #Huynh
        if not parsed.success:
            payment = await self._expire_if_overdue(payment)
        elif payment.expires_at <= datetime.now(UTC):
            log.warning(
                "payments.succeeded_after_expiry",
                order_id=parsed.order_id,
                expires_at=payment.expires_at.isoformat(),
                hint="Vẫn kích hoạt vì tiền đã thu thật. Kiểm tra vì sao IPN tới muộn.",
            )

        if payment.status != SubscriptionPaymentStatus.PENDING:
            # Idempotent replay — providers retry callbacks until acked.
            log.info(
                "payments.callback_replay_ignored",
                order_id=parsed.order_id,
                status=str(payment.status),
            )
            return gateway.build_ack_response(parsed)

        entity = _payment_to_entity(payment)
        now = datetime.now(UTC)
        if parsed.success:
            plan = await self.repo.get_plan(payment.plan_id)
            subscription = await self.repo.get_subscription(payment.user_id)

            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=_BILLING_PERIOD_DAYS)
            await self.repo.save(subscription)

            # Through the domain entity so the PENDING invariant it enforces
            # isn't bypassed — matches cancel_checkout's pattern above.
            entity.mark_succeeded(parsed.provider_reference)
            payment.status = entity.status.value
            payment.provider_reference = entity.provider_reference
            payment.paid_at = entity.paid_at
            payment.updated_at = entity.updated_at
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
            log.info(
                "payments.subscription_activated",
                order_id=parsed.order_id,
                user_id=str(payment.user_id),
                plan_id=str(plan.id),
                amount=str(payment.amount),
                currency=payment.currency,
            )
        else:
            entity.mark_failed(parsed.message)
            payment.status = entity.status.value
            payment.failure_reason = entity.failure_reason
            payment.updated_at = entity.updated_at
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
            log.info(
                "payments.payment_failed",
                order_id=parsed.order_id,
                user_id=str(payment.user_id),
                reason=parsed.message,
            )

        return gateway.build_ack_response(parsed)

    async def get_my_subscription(self, user_id: uuid.UUID) -> SubscriptionResponse:
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No active subscription found")

        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None:
            raise NotFoundError("Subscription plan not found")

        return self._to_subscription_response(sub, plan)

    async def cancel_subscription(self, user_id: uuid.UUID) -> SubscriptionResponse:
        """Schedule the caller's subscription to lapse at the end of the current
        billing period — access and entitlements are unaffected until then.
        `expire_lapsed_subscriptions` is what actually downgrades the plan
        once `current_period_end` passes."""
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No subscription found")

        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None:
            raise NotFoundError("Subscription plan not found")
        if plan.price_monthly <= 0:
            raise SubscriptionNotCancellableError("The free plan cannot be cancelled")
        if sub.cancel_at_period_end:
            raise SubscriptionNotCancellableError("Subscription is already scheduled to cancel")

        sub.cancel_at_period_end = True
        sub.cancelled_at = datetime.now(UTC)
        sub = await self.repo.save(sub)
        return self._to_subscription_response(sub, plan)

    async def expire_lapsed_subscriptions(self) -> int:
        """Downgrade every subscription whose paid period has ended back to
        the free plan. There's no recurring auto-charge — MoMo checkout is a
        one-time, user-initiated action — so staying on a paid plan requires a
        fresh checkout before `current_period_end`, whether or not the user
        explicitly cancelled. Meant to be run periodically by Celery Beat.
        """
        free_plan = await self.repo.get_free_plan()
        if free_plan is None:
            return 0

        now = datetime.now(UTC)
        lapsed = await self.repo.list_lapsed_subscriptions(free_plan_id=free_plan.id, now=now)

        for sub in lapsed:
            await self.repo.create_billing_event(
                user_id=sub.user_id,
                subscription_id=sub.id,
                event_type=(
                    "subscription_cancelled" if sub.cancel_at_period_end else "subscription_expired"
                ),
                amount=Decimal("0"),
                currency="VND",
                event_metadata={"previous_plan_id": str(sub.plan_id)},
            )
            sub.plan_id = free_plan.id
            sub.status = "active"
            sub.cancel_at_period_end = False
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=_FREE_PLAN_PERIOD_DAYS)
            await self.repo.save(sub)

        return len(lapsed)

    @staticmethod
    def _to_subscription_response(sub, plan) -> SubscriptionResponse:
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
