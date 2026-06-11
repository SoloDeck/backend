import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.users.domain.value_objects.preferences import Preferences
from src.modules.users.domain.value_objects.professional_profile import ProfessionalProfile
from src.modules.users.domain.value_objects.user_status import UserRole, UserStatus


@dataclass
class User:
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    hashed_password: str | None     # None for OAuth-only accounts
    avatar_url: str | None
    bio: str | None
    phone: str | None
    professional_profile: ProfessionalProfile
    preferences: Preferences
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        return self.status == UserStatus.SUSPENDED

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def can_login_with_password(self) -> bool:
        return self.hashed_password is not None

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def update_profile(
        self,
        full_name: str | None = None,
        avatar_url: str | None = None,
        bio: str | None = None,
        phone: str | None = None,
    ) -> None:
        from src.modules.users.domain.exceptions.exceptions import UserAlreadyDeletedError
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        if full_name is not None:
            if not full_name.strip():
                raise ValueError("Full name must not be blank")
            self.full_name = full_name.strip()
        if avatar_url is not None:
            self.avatar_url = avatar_url
        if bio is not None:
            self.bio = bio
        if phone is not None:
            self.phone = phone
        self.updated_at = datetime.now(UTC)

    def update_professional_profile(self, profile: ProfessionalProfile) -> None:
        from src.modules.users.domain.exceptions.exceptions import UserAlreadyDeletedError
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        self.professional_profile = profile
        self.updated_at = datetime.now(UTC)

    def update_preferences(self, preferences: Preferences) -> None:
        from src.modules.users.domain.exceptions.exceptions import UserAlreadyDeletedError
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        self.preferences = preferences
        self.updated_at = datetime.now(UTC)

    def suspend(self) -> None:
        from src.modules.users.domain.exceptions.exceptions import (
            InvalidUserStatusTransitionError,
            UserAlreadyDeletedError,
        )
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        if not self.is_active:
            raise InvalidUserStatusTransitionError(self.status, UserStatus.SUSPENDED)
        self.status = UserStatus.SUSPENDED
        self.updated_at = datetime.now(UTC)

    def reactivate(self) -> None:
        from src.modules.users.domain.exceptions.exceptions import (
            InvalidUserStatusTransitionError,
            UserAlreadyDeletedError,
        )
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        if not self.is_suspended:
            raise InvalidUserStatusTransitionError(self.status, UserStatus.ACTIVE)
        self.status = UserStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

    def soft_delete(self) -> None:
        from src.modules.users.domain.exceptions.exceptions import UserAlreadyDeletedError
        if self.is_deleted:
            raise UserAlreadyDeletedError()
        now = datetime.now(UTC)
        self.status = UserStatus.DELETED
        self.deleted_at = now
        self.updated_at = now
