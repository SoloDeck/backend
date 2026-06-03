"""Reminders application service — skeleton."""
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

@dataclass
class RemindersService:
    db: AsyncSession
