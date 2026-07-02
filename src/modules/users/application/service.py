"""Users application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.infrastructure.repository import UsersRepository
from src.modules.users.schemas.request import (
    ChangePasswordRequest,
    FreelancerProfileUpdateRequest,
    UpdateUserRequest,
)
from src.shared.exceptions.domain import AuthenticationError, NotFoundError
from src.shared.security.passwords import hash_password, verify_password


@dataclass
class UsersService:
    db: AsyncSession
    repo: UsersRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = UsersRepository(self.db)

    async def get_me(self, user_id: uuid.UUID):  # type: ignore[return]
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def update_me(self, user_id: uuid.UUID, payload: UpdateUserRequest):  # type: ignore[return]
        user = await self.get_me(user_id)
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.phone is not None:
            user.phone = payload.phone
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url
        return await self.repo.save(user)

    async def delete_me(self, user_id: uuid.UUID) -> None:
        user = await self.get_me(user_id)
        user.deleted_at = datetime.now(UTC)
        user.status = "deleted"
        await self.repo.save(user)

    async def update_freelancer_profile(
        self, user_id: uuid.UUID, payload: FreelancerProfileUpdateRequest
    ):  # type: ignore[return]
        user = await self.get_me(user_id)
        for field in payload.model_fields_set:
            setattr(user, field, getattr(payload, field))
        return await self.repo.save(user)

    async def change_password(self, user_id: uuid.UUID, payload: ChangePasswordRequest) -> None:
        user = await self.get_me(user_id)
        if user.hashed_password is None or not verify_password(
            payload.current_password, user.hashed_password
        ):
            raise AuthenticationError("Current password is incorrect")
        user.hashed_password = hash_password(payload.new_password)
        await self.repo.save(user)
