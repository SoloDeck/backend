import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ReminderModel


@dataclass
class RemindersRepository:
    db: AsyncSession

    async def get_by_id(self, reminder_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ReminderModel).where(
                ReminderModel.id == reminder_id,
                ReminderModel.owner_user_id == owner_user_id,
            )
        )

    async def create(self, **values):
        reminder = ReminderModel(**values)
        self.db.add(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        return reminder

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        target_type: str | None = None,
    ) -> list:
        conditions = [ReminderModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(ReminderModel.status == status)
        if target_type is not None:
            conditions.append(ReminderModel.target_type == target_type)
        result = await self.db.execute(select(ReminderModel).where(*conditions))
        return list(result.scalars().all())

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
