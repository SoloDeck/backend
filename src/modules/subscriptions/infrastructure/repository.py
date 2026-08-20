import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    BillingEventModel,
    PlanModel,
    SubscriptionModel,
    SubscriptionPaymentModel,
)


@dataclass
class SubscriptionsRepository:
    db: AsyncSession

    async def list_active_plans(self) -> list:
        result = await self.db.execute(select(PlanModel).where(PlanModel.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_subscription(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def get_free_plan(self):
        """Gói miễn phí — tra theo MÃ (`slug`), không theo TÊN.

        Bản cũ tra ``name == "Free"``. `auth/infrastructure/repository.py` đã sửa đúng
        chuyện này rồi và ghi rõ lý do, nhưng bản ở đây bị bỏ sót — mà đây mới là bản
        `expire_lapsed_subscriptions` gọi.

        Hậu quả của chỗ sót: admin đổi tên gói thành "Miễn phí" qua màn quản trị là job
        hạ gói **ngừng hoạt động trong im lặng** — `get_free_plan()` trả None, hàm gọi
        `return 0` và không log gì. Người hết hạn gói trả phí giữ nguyên quyền lợi trả
        phí vĩnh viễn, không ai biết cho tới lúc đối soát doanh thu.

        Tên để hiển thị (đổi thoải mái), mã là khoá code.  #Huynh
        """
        return await self.db.scalar(select(PlanModel).where(PlanModel.slug == "free"))

    async def list_lapsed_subscriptions(self, *, free_plan_id: uuid.UUID, now: datetime):
        """Paid subscriptions whose current billing period has already ended.

        Locked for update — a concurrent checkout webhook extending one of
        these subscriptions' period must not race with this batch downgrade.
        """
        result = await self.db.execute(
            select(SubscriptionModel)
            .where(
                SubscriptionModel.plan_id != free_plan_id,
                SubscriptionModel.current_period_end <= now,
            )
            .with_for_update()
        )
        return list(result.scalars().all())

    async def create_payment(self, **values):
        payment = SubscriptionPaymentModel(**values)
        self.db.add(payment)
        await self.db.flush()
        await self.db.refresh(payment)
        return payment

    async def get_payment_by_id(self, payment_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionPaymentModel).where(SubscriptionPaymentModel.id == payment_id)
        )

    async def get_payment_by_id_for_update(self, payment_id: uuid.UUID):
        """Like `get_payment_by_id`, but takes a row lock held until commit/rollback.

        Concurrent webhook deliveries for the same order (providers retry on
        timeout) must be serialized — otherwise two callbacks can both read
        status=PENDING before either commits and both activate the
        subscription / write a billing event.
        """
        return await self.db.scalar(
            select(SubscriptionPaymentModel)
            .where(SubscriptionPaymentModel.id == payment_id)
            .with_for_update()
        )

    async def get_payment_by_order_code_for_update(self, order_code: str):
        """Như `get_payment_by_id_for_update`, nhưng tra theo mã đơn ngắn.

        Cùng khoá hàng, cùng lý do: một cổng có thể giao lại callback nhiều lần.
        """
        return await self.db.scalar(
            select(SubscriptionPaymentModel)
            .where(SubscriptionPaymentModel.order_code == order_code)
            .with_for_update()
        )

    async def create_billing_event(self, **values):
        event = BillingEventModel(**values)
        self.db.add(event)
        await self.db.flush()
        return event

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
