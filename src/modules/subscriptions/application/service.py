"""Subscriptions application service."""

import uuid
from collections.abc import Mapping
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
    generate_order_code,
)
from src.modules.subscriptions.domain.exceptions.exceptions import (
    InvalidPaymentSignatureError,
    PlanNotPurchasableError,
    SubscriptionNotCancellableError,
)
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.modules.subscriptions.infrastructure.repository import SubscriptionsRepository
from src.modules.subscriptions.schemas.response import SubscriptionResponse, UsageRecordResponse
from src.shared.exceptions.domain import DomainError, NotFoundError

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
    zalopay_client: PaymentGateway | None = None
    sepay_client: PaymentGateway | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = SubscriptionsRepository(self.db)

    def _gateway(self, provider: PaymentProvider) -> PaymentGateway:
        """Adapter cho cổng được chọn.

        Bản trước hard-code `provider != PaymentProvider.MOMO`, nên thêm cổng thứ hai là
        phải sửa đúng dòng này — dễ quên, và quên thì mọi checkout ZaloPay chết bằng một
        `RuntimeError` 500 trần. Giữ dạng bảng để cổng thứ ba chỉ là thêm một dòng.
        """
        gateway = {
            PaymentProvider.MOMO: self.momo_client,
            PaymentProvider.ZALOPAY: self.zalopay_client,
            PaymentProvider.SEPAY: self.sepay_client,
        }.get(provider)
        if gateway is None:
            raise RuntimeError(f"No payment gateway configured for provider '{provider}'")
        return gateway

    @staticmethod
    def _notify_url(provider: PaymentProvider) -> str:
        """Webhook server-to-server của TỪNG cổng.

        Bản trước truyền thẳng `settings.momo_ipn_url` cho mọi provider. Với một cổng thì
        vô hại; với hai cổng thì ZaloPay sẽ gọi callback vào đúng cái webhook của MoMo —
        payload đi lạc đường, chữ ký không bao giờ khớp, và tiền đã thu thật thì không
        bao giờ kích hoạt được gói.
        """
        return {
            PaymentProvider.MOMO: settings.momo_ipn_url,
            PaymentProvider.ZALOPAY: settings.zalopay_callback_url,
            # SePay cau hinh webhook MOT LAN tren dashboard chu khong nhan URL theo tung
            # don. Gia tri nay chi de adapter khop protocol va de doi chieu khi debug.
            PaymentProvider.SEPAY: settings.sepay_callback_url,
        }[provider]

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

        # Sinh MỘT LẦN vào biến rồi dùng lại cho cả lúc ghi lẫn lúc gửi sang cổng. Đọc
        # ngược `payment.order_code` từ bản ghi vừa tạo cũng ra đúng giá trị, nhưng lúc đó
        # đường đi của dữ liệu phụ thuộc vào việc repo có trả lại nguyên vẹn hay không —
        # một ràng buộc ngầm, không có gì bắt lỗi nếu nó hỏng.
        order_code = generate_order_code()
        payment = await self.repo.create_payment(
            user_id=user_id,
            subscription_id=subscription.id,
            plan_id=plan.id,
            provider=provider.value,
            status=SubscriptionPaymentStatus.PENDING.value,
            amount=plan.price_monthly,
            currency=plan.currency,
            order_code=order_code,
            expires_at=datetime.now(UTC) + timedelta(minutes=_CHECKOUT_TTL_MINUTES),
        )

        gateway = self._gateway(provider)
        result = await gateway.create_payment(
            order_id=str(payment.id),
            amount=plan.price_monthly,
            currency=plan.currency,
            order_info=f"SoloDesk {plan.name} plan upgrade",
            notify_url=self._notify_url(provider),
            redirect_url=return_url,
            order_code=order_code,
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

    async def _payment_for_callback(self, order_id: str):
        """Tra bản ghi thanh toán từ mã đơn provider gửi về — UUID HOẶC mã đơn ngắn.

        MoMo/ZaloPay trả lại chính `payment.id` (UUID). Cổng đối soát ngân hàng chỉ biết
        mã ngắn `SD7K2M9PQR` đọc được từ nội dung chuyển khoản. Thử UUID trước, không phải
        UUID thì tra theo `order_code` — CHỨ KHÔNG phải báo 404 ngay như bản trước.

        Cả hai đường đều khoá hàng (`with_for_update`): một cổng có thể giao lại callback
        nhiều lần, và hai lần giao song song đều đọc thấy PENDING là kích hoạt gói hai lần.
        """
        try:
            payment_id = uuid.UUID(order_id)
        except (ValueError, AttributeError, TypeError):
            return await self.repo.get_payment_by_order_code_for_update(str(order_id))
        return await self.repo.get_payment_by_id_for_update(payment_id)

    async def handle_payment_callback(
        self,
        provider: PaymentProvider,
        raw_payload: dict,
        headers: Mapping[str, str] | None = None,
    ) -> dict:
        """`headers` là header HTTP của chính request webhook.

        Bắt buộc phải truyền xuống từ router: cổng kiểu đối soát ngân hàng xác thực bằng
        header `Authorization` chứ không ký trong thân request. Xem docstring của
        `PaymentGateway.verify_callback_signature`.
        """
        gateway = self._gateway(provider)
        if not gateway.verify_callback_signature(raw_payload, headers):
            raise InvalidPaymentSignatureError()
        parsed = gateway.parse_callback(raw_payload)

        log.info(
            "payments.callback_received",
            provider=provider.value,
            order_id=parsed.order_id,
            success=parsed.success,
        )

        # Row lock held until this request commits/rolls back — serializes
        # concurrent deliveries of the same callback so only one can pass the
        # PENDING check below.
        # Su kien khong lien quan toi don nao (vd SePay bao mot khoan CHUYEN DI). Ack roi
        # dung han: tra ve bat ky ma loi nao o day chi khien provider gui lai mai mot su
        # kien khong bao gio khop duoc don nao.
        if not parsed.actionable:
            log.info(
                "payments.callback_not_actionable",
                provider=provider.value,
                reason=parsed.message,
            )
            return gateway.build_ack_response(parsed)

        payment = await self._payment_for_callback(parsed.order_id)
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

        # Số tiền provider BÁO ĐÃ THU phải khớp số ta yêu cầu.
        #
        # Chữ ký HMAC đã phủ `amount` nên không ai giả mạo được — đây KHÔNG phải lỗ hổng
        # bảo mật, mà là chốt chặn cho trường hợp lệch thật: cấu hình sai, thu thiếu, hay
        # một thay đổi phía MoMo. Lệch mà vẫn kích hoạt là biếu không cả gói dịch vụ.
        #
        # KHÁC với ca đến muộn ở trên (vẫn kích hoạt vì tiền khớp, chỉ chậm): ở đây ta
        # KHÔNG biết người dùng đã mua cái gì, nên không đoán bừa. Đánh dấu thất bại kèm lý
        # do, log mức `error` để có người xử tay (hoàn tiền hoặc kích hoạt thủ công) — thà
        # lộ ra và bị phàn nàn còn hơn âm thầm thất thoát doanh thu.
        #
        # `amount is None` thì bỏ qua kiểm: provider không gửi thì không có gì để đối chiếu,
        # và chặn ở đây là chặn oan mọi giao dịch.  #Huynh
        if parsed.success and parsed.amount is not None and parsed.amount != payment.amount:
            log.error(
                "payments.amount_mismatch",
                order_id=parsed.order_id,
                expected=str(payment.amount),
                received=str(parsed.amount),
                hint="KHÔNG kích hoạt gói. Cần người kiểm tra và xử lý tay.",
            )
            parsed = parsed._replace(
                success=False,
                message=(
                    f"Số tiền không khớp: yêu cầu {payment.amount} {payment.currency}, "
                    f"nhận {parsed.amount}."
                ),
            )

        entity = _payment_to_entity(payment)
        now = datetime.now(UTC)
        if parsed.success:
            plan = await self.repo.get_plan(payment.plan_id)
            subscription = await self.repo.get_subscription(payment.user_id)

            # Gói hoặc thuê bao biến mất giữa lúc người dùng đang trả tiền (admin xoá gói,
            # dữ liệu lệch). Không chặn ở đây thì `plan.id` ném `AttributeError` — một 500
            # trần không nói được gì. `initiate_checkout` vốn đã kiểm None; nhánh callback
            # thì bỏ sót.
            #
            # Ở đây NÉM lỗi (→ 404, MoMo sẽ retry) chứ không đánh dấu thất bại như ca lệch
            # tiền bên trên. Khác nhau ở chỗ CÓ SỬA ĐƯỢC KHÔNG: lệch tiền thì retry bao
            # nhiêu lần cũng vẫn lệch, nên đóng lại luôn; còn gói bị xoá thì admin khôi
            # phục xong, lần retry kế tiếp tự kích hoạt được — giữ đường cho nó tự lành.
            # #Huynh
            if plan is None or subscription is None:
                log.error(
                    "payments.activation_target_missing",
                    order_id=parsed.order_id,
                    plan_found=plan is not None,
                    subscription_found=subscription is not None,
                    hint="Đã thu tiền nhưng không kích hoạt được. Cần xử lý tay.",
                )
                raise NotFoundError(
                    "Không tìm thấy gói hoặc thuê bao để kích hoạt cho khoản thanh toán này."
                )

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

    async def upgrade_subscription(
        self, user_id: uuid.UUID, plan_id: uuid.UUID
    ) -> SubscriptionResponse:
        """Immediate plan switch — starts a fresh billing period now (same convention
        as a confirmed checkout payment, see handle_payment_callback), so AI quota
        naturally reads as 0 used for the new period without a separate reset step."""
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No subscription found")
        current_plan = await self.repo.get_plan(sub.plan_id)
        new_plan = await self.repo.get_plan(plan_id)
        if new_plan is None or not new_plan.is_active:
            raise NotFoundError(f"Plan {plan_id} not found")
        if current_plan is not None and new_plan.price_monthly <= current_plan.price_monthly:
            raise DomainError(
                "Target plan is not more expensive than the current plan. "
                "Use /subscriptions/me/downgrade instead."
            )

        now = datetime.now(UTC)
        sub.plan_id = new_plan.id
        sub.status = "active"
        sub.cancel_at_period_end = False
        sub.cancelled_at = None
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=_BILLING_PERIOD_DAYS)
        sub = await self.repo.save(sub)

        await self.repo.create_billing_event(
            user_id=user_id,
            subscription_id=sub.id,
            event_type="subscription_upgraded",
            amount=Decimal("0"),
            currency="VND",
            event_metadata={
                "previous_plan_id": str(current_plan.id) if current_plan else None,
                "new_plan_id": str(new_plan.id),
            },
        )
        return self._to_subscription_response(sub, new_plan)

    async def downgrade_subscription(
        self, user_id: uuid.UUID, plan_id: uuid.UUID
    ) -> SubscriptionResponse:
        """Schedules a lapse at current_period_end — the same mechanism as
        cancel_subscription (cancel_at_period_end=True), since expire_lapsed_subscriptions
        only knows how to land a lapsed subscription on the FREE plan, not on an
        arbitrary specific paid tier. `plan_id` is validated (must be cheaper than the
        current plan) and recorded on the billing event for audit purposes, but does
        NOT currently change what plan the user lands on at period end — that's always
        free, exactly like an explicit cancel. Landing on a specific cheaper PAID plan
        would need a scheduled-plan-id column and updated expiry logic; out of scope here.
        """
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No subscription found")
        current_plan = await self.repo.get_plan(sub.plan_id)
        new_plan = await self.repo.get_plan(plan_id)
        if new_plan is None or not new_plan.is_active:
            raise NotFoundError(f"Plan {plan_id} not found")
        if current_plan is not None and new_plan.price_monthly >= current_plan.price_monthly:
            raise DomainError(
                "Target plan is not cheaper than the current plan. "
                "Use /subscriptions/me/upgrade instead."
            )
        if sub.cancel_at_period_end:
            raise SubscriptionNotCancellableError(
                "Subscription is already scheduled to change at period end"
            )

        sub.cancel_at_period_end = True
        sub.cancelled_at = datetime.now(UTC)
        sub = await self.repo.save(sub)

        await self.repo.create_billing_event(
            user_id=user_id,
            subscription_id=sub.id,
            event_type="subscription_downgrade_scheduled",
            amount=Decimal("0"),
            currency="VND",
            event_metadata={"requested_plan_id": str(new_plan.id)},
        )
        return self._to_subscription_response(sub, current_plan)

    async def get_usage(self, user_id: uuid.UUID) -> UsageRecordResponse:
        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise NotFoundError("No subscription found")
        summary = await AiUsageService(self.db).summary(user_id)
        return UsageRecordResponse(
            user_id=user_id,
            billing_period_start=summary["period_start"],
            billing_period_end=summary["period_end"],
            ai_generations_used=summary["used"],
            ai_generations_limit=summary["limit"],
        )

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
