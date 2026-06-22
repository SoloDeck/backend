import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import PlanModel, UserModel


@dataclass
class AdminRepository:
    db: AsyncSession

    async def list_users(self) -> list:
        result = await self.db.execute(
            select(UserModel).where(UserModel.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
        )

    async def list_plans(self) -> list:
        result = await self.db.execute(select(PlanModel))
        return list(result.scalars().all())

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def create_plan(self, **values):
        plan = PlanModel(**values)
        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)
        return plan

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
