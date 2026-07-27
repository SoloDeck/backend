"""Đường DB riêng của module Zalo (theo AGENTS.md, không dùng chung repo module khác)."""

import uuid
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ClientModel, UserModel

_T = TypeVar("_T")


@dataclass
class ZaloRepository:
    db: AsyncSession

    async def get_user(self, user_id: uuid.UUID) -> UserModel | None:
        user: UserModel | None = await self.db.scalar(
            select(UserModel).where(UserModel.id == user_id)
        )
        return user

    async def get_user_by_oa_id(self, oa_id: str) -> UserModel | None:
        """Freelancer sở hữu OA này — dùng ở webhook để biết sự kiện thuộc về ai."""
        user: UserModel | None = await self.db.scalar(
            select(UserModel).where(UserModel.zalo_oa_app_id == oa_id)
        )
        return user

    async def get_client_by_phone(
        self, owner_user_id: uuid.UUID, phone: str
    ) -> ClientModel | None:
        """Khách của freelancer khớp số điện thoại (chưa xoá mềm)."""
        client: ClientModel | None = await self.db.scalar(
            select(ClientModel).where(
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.phone == phone,
                ClientModel.deleted_at.is_(None),
            )
        )
        return client

    async def save(self, obj: _T) -> _T:
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
