"""Admin domain exceptions.

Subclass the shared `BusinessRuleError`/`ValidationError` (not a private
per-module base) so they get real HTTP translation via
`src/shared/exceptions/http.py`'s registered handlers.
"""

import uuid
from datetime import datetime

from src.shared.exceptions.domain import BusinessRuleError, ValidationError


class LastAdminSuspensionError(BusinessRuleError):
    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"Cannot suspend user {user_id}: they are the last active admin")
        self.user_id = user_id


class InvalidRolloutPercentageError(ValidationError):
    def __init__(self, rollout_percentage: int) -> None:
        super().__init__(
            f"rollout_percentage must be between 0 and 100, got {rollout_percentage}"
        )
        self.rollout_percentage = rollout_percentage


class OverrideExpiryInPastError(ValidationError):
    def __init__(self, override_expires_at: datetime) -> None:
        super().__init__(
            f"override_expires_at must be in the future, got {override_expires_at.isoformat()}"
        )
        self.override_expires_at = override_expires_at
