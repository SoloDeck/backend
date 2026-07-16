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

    async def get_by_phone(self, phone: str, *, exclude_user_id: uuid.UUID | None = None):
        stmt = select(UserModel).where(
            UserModel.phone == phone,
            UserModel.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return await self.db.scalar(stmt)

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
