import uuid
from dataclasses import dataclass

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

    async def create_billing_event(self, **values):
        event = BillingEventModel(**values)
        self.db.add(event)
        await self.db.flush()
        return event

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
