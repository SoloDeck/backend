"""Subscriptions application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import NotFoundError
from src.modules.subscriptions.schemas.response import SubscriptionResponse


@dataclass
class SubscriptionsService:
    db: AsyncSession

    async def list_plans(self) -> list:
        from src.infrastructure.database.models import PlanModel

        result = await self.db.execute(
            select(PlanModel).where(PlanModel.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def get_my_subscription(self, user_id: uuid.UUID) -> SubscriptionResponse:
        from src.infrastructure.database.models import SubscriptionModel, PlanModel

        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is None:
            raise NotFoundError("No active subscription found")

        plan = await self.db.scalar(
            select(PlanModel).where(PlanModel.id == sub.plan_id)
        )
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
