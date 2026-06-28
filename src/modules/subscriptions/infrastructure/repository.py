import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import PlanModel, SubscriptionModel


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
