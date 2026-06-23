"""Reminders application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reminders.infrastructure.repository import RemindersRepository
from src.modules.reminders.schemas.request import ReminderRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class RemindersService:
    db: AsyncSession
    repo: RemindersRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = RemindersRepository(self.db)

    async def _get_reminder(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        reminder = await self.repo.get_by_id(reminder_id, user_id)
        if reminder is None:
            raise NotFoundError(f"Reminder {reminder_id} not found")
        return reminder

    async def create(self, user_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        return await self.repo.create(
            owner_user_id=user_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            reminder_type=payload.reminder_type,
            channel=payload.channel,
            status="pending",
            scheduled_at=payload.scheduled_at,
            message_preview=payload.message_preview,
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        target_type: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, status=status, target_type=target_type)

    async def get_one(self, user_id: uuid.UUID, reminder_id: uuid.UUID):  # type: ignore[return]
        return await self._get_reminder(user_id, reminder_id)

    async def update(self, user_id: uuid.UUID, reminder_id: uuid.UUID, payload: ReminderRequest):  # type: ignore[return]
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.scheduled_at = payload.scheduled_at
        reminder.message_preview = payload.message_preview
        reminder.channel = payload.channel
        return await self.repo.save(reminder)

    async def cancel(self, user_id: uuid.UUID, reminder_id: uuid.UUID) -> None:
        reminder = await self._get_reminder(user_id, reminder_id)
        reminder.status = "cancelled"
        await self.repo.save(reminder)
