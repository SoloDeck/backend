import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import UserModel


@dataclass
class UsersRepository:
    db: AsyncSession

    async def get_by_id(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
        )

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
