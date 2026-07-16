"""Users application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import UserModel
from src.integrations.storage.client import StorageClient
from src.modules.users.infrastructure.repository import UsersRepository
from src.modules.users.schemas.request import (
    ChangePasswordRequest,
    FreelancerProfileUpdateRequest,
    UpdatePreferencesRequest,
    UpdateProfessionalProfileRequest,
    UpdateUserRequest,
)
from src.shared.exceptions.domain import (
    AlreadyExistsError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from src.shared.security.passwords import hash_password, verify_password

AVATAR_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
AVATAR_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@dataclass
class UsersService:
    db: AsyncSession
    repo: UsersRepository | None = None
    storage: StorageClient | None = None

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
            existing = await self.repo.get_by_phone(payload.phone, exclude_user_id=user_id)
            if existing is not None:
                raise AlreadyExistsError(f"Phone '{payload.phone}' is already in use")
            user.phone = payload.phone
        if payload.avatar_url is not None:
            user.avatar_url = payload.avatar_url
        if payload.bio is not None:
            user.bio = payload.bio
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

    async def update_professional_profile(
        self, user_id: uuid.UUID, payload: UpdateProfessionalProfileRequest
    ):  # type: ignore[return]
        user = await self.get_me(user_id)
        if payload.skills is not None:
            user.skills = payload.skills
        if payload.specialization is not None:
            user.specialization = payload.specialization
        if payload.default_hourly_rate is not None:
            user.default_hourly_rate = payload.default_hourly_rate
        if payload.currency is not None:
            user.currency = payload.currency
        if payload.portfolio_url is not None:
            user.portfolio_url = payload.portfolio_url
        if payload.business_name is not None:
            user.business_name = payload.business_name
        return await self.repo.save(user)

    async def update_preferences(
        self, user_id: uuid.UUID, payload: UpdatePreferencesRequest
    ):  # type: ignore[return]
        user = await self.get_me(user_id)
        if payload.locale is not None:
            user.locale = payload.locale
        if payload.timezone is not None:
            user.timezone = payload.timezone
        if payload.notification_channel is not None:
            user.notification_channel = payload.notification_channel
        if payload.theme is not None:
            user.theme = payload.theme
        return await self.repo.save(user)

    async def change_password(self, user_id: uuid.UUID, payload: ChangePasswordRequest) -> None:
        user = await self.get_me(user_id)
        if user.hashed_password is None or not verify_password(
            payload.current_password, user.hashed_password
        ):
            raise AuthenticationError("Current password is incorrect")
        user.hashed_password = hash_password(payload.new_password)
        await self.repo.save(user)

    async def upload_avatar(
        self, user_id: uuid.UUID, *, content: bytes, content_type: str
    ) -> UserModel:
        if self.storage is None:
            raise RuntimeError("Storage client not initialized")
        if content_type not in AVATAR_EXTENSION_BY_CONTENT_TYPE:
            raise ValidationError(
                f"Unsupported image type '{content_type}'. Allowed: jpeg, png, webp."
            )
        if not content:
            raise ValidationError("Avatar file is empty")
        if len(content) > AVATAR_MAX_SIZE_BYTES:
            raise ValidationError("Avatar image must be 5MB or smaller")

        user = await self.get_me(user_id)
        ext = AVATAR_EXTENSION_BY_CONTENT_TYPE[content_type]
        key = f"avatars/{user_id}/{uuid.uuid4().hex}.{ext}"
        user.avatar_url = await self.storage.upload(
            key=key, content=content, content_type=content_type
        )
        return await self.repo.save(user)
