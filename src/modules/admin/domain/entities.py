"""Admin domain entities.

Pure Python dataclasses encoding the business invariants of platform
administration actions. No I/O, no SQLAlchemy — the service layer
constructs these from ORM rows, calls their commands, then writes the
resulting state back via the repository.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from src.modules.admin.domain.exceptions import (
    InvalidRolloutPercentageError,
    LastAdminSuspensionError,
    OverrideExpiryInPastError,
)

UserRole = Literal["freelancer", "admin"]
UserStatus = Literal["active", "suspended", "deleted"]


@dataclass
class AdminUser:
    """A platform user as seen by admin moderation actions."""

    id: uuid.UUID
    email: str
    role: UserRole
    status: UserStatus

    def suspend(self, *, is_last_active_admin: bool) -> None:
        """Suspend the user, refusing to lock out the platform's last admin."""
        if self.role == "admin" and is_last_active_admin:
            raise LastAdminSuspensionError(self.id)
        self.status = "suspended"

    def reinstate(self) -> None:
        self.status = "active"


@dataclass
class SubscriptionOverride:
    """An admin's manual override of a user's subscription plan/expiry."""

    subscription_id: uuid.UUID
    plan_id: uuid.UUID
    override_by_admin_id: uuid.UUID
    override_expires_at: datetime | None

    def __post_init__(self) -> None:
        if self.override_expires_at is not None and self.override_expires_at <= datetime.now(UTC):
            raise OverrideExpiryInPastError(self.override_expires_at)


@dataclass
class FeatureFlagRollout:
    """A feature flag's rollout configuration and per-user resolution."""

    flag_name: str
    is_enabled: bool
    rollout_percentage: int
    target_user_ids: list[uuid.UUID] | None

    def __post_init__(self) -> None:
        if not 0 <= self.rollout_percentage <= 100:
            raise InvalidRolloutPercentageError(self.rollout_percentage)

    def is_enabled_for_user(self, user_id: uuid.UUID) -> bool:
        """Whether this flag resolves to "on" for a specific user.

        Explicit `target_user_ids` always win. Otherwise a user falls into a
        stable 0-99 bucket (hash of flag name + user id) compared against the
        rollout percentage, so the same user always gets the same result for
        a given flag/percentage rather than flipping on every call.
        """
        if not self.is_enabled:
            return False
        if self.target_user_ids and user_id in self.target_user_ids:
            return True
        if self.rollout_percentage >= 100:
            return True
        if self.rollout_percentage <= 0:
            return False
        digest = hashlib.sha256(f"{self.flag_name}:{user_id}".encode()).hexdigest()
        bucket = int(digest, 16) % 100
        return bucket < self.rollout_percentage
