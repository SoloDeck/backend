"""Reminders application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reminders.schemas.request import ReminderRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class RemindersService:
    db: AsyncSession

    async def _get_reminder(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import ReminderModel

        reminder = await self.db.scalar(
            select(ReminderModel).where(
                ReminderModel.id == reminder_id,
                ReminderModel.owner_user_id == user_id,
            )
        )
        if reminder is None:
            raise NotFoundError(f"Reminder {reminder_id} not found")
        return reminder

    async def create(self, user_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ReminderModel

        reminder = ReminderModel(
            owner_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            reminder_type=payload.reminder_type,
            channel=payload.channel,
            status="pending",
            scheduled_at=payload.scheduled_at,
            message_preview=payload.message_preview,
        )
        self.db.add(reminder)
        await self.db.flush()
        await self.db.refresh(reminder)
        return reminder

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ReminderModel

        result = await self.db.execute(
            select(ReminderModel).where(ReminderModel.owner_user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        return await self._get_reminder(user_id, reminder_id)

    async def update(self, user_id: uuid.UUID, reminder_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.scheduled_at = payload.scheduled_at
        reminder.message_preview = payload.message_preview
        reminder.channel = payload.channel
        await self.db.flush()
        await self.db.refresh(reminder)
        return reminder

    async def cancel(self, user_id: uuid.UUID, reminder_id: uuid.UUID) -> None:
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.status = "cancelled"
        await self.db.flush()
