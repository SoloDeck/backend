import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from src.modules.reminders.domain.value_objects.reminder_status import (
    TERMINAL_REMINDER_STATUSES,
    ReminderStatus,
)
from src.modules.reminders.domain.value_objects.reminder_target import (
    ReminderTarget,
)


class ReminderType(StrEnum):
    FOLLOW_UP = "follow_up"
    PROPOSAL_FOLLOW_UP = "proposal_follow_up"
    CONTRACT_SIGNING_NUDGE = "contract_signing_nudge"
    PAYMENT_DUE = "payment_due"
    PAYMENT_OVERDUE = "payment_overdue"
    RE_ENGAGEMENT = "re_engagement"
    CUSTOM = "custom"


@dataclass
class Reminder:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    target: ReminderTarget
    reminder_type: ReminderType
    channel: str  # "email" | "zalo" | "in_app"
    message: str
    scheduled_at: datetime
    status: ReminderStatus
    is_recurring: bool
    recurrence_interval_days: int | None
    recurrence_end_date: datetime | None
    sent_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_REMINDER_STATUSES

    @property
    def is_cancellable(self) -> bool:
        return self.status == ReminderStatus.PENDING

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def mark_sent(self) -> None:
        from src.modules.reminders.domain.exceptions.exceptions import TerminalReminderError

        if self.is_terminal:
            raise TerminalReminderError(self.status)
        now = datetime.now(UTC)
        self.status = ReminderStatus.SENT
        self.sent_at = now
        self.updated_at = now

    def mark_failed(self) -> None:
        from src.modules.reminders.domain.exceptions.exceptions import TerminalReminderError

        if self.is_terminal:
            raise TerminalReminderError(self.status)
        self.status = ReminderStatus.FAILED
        self.updated_at = datetime.now(UTC)

    def cancel(self, reason: str | None = None) -> None:
        from src.modules.reminders.domain.exceptions.exceptions import ReminderNotCancellableError

        if not self.is_cancellable:
            raise ReminderNotCancellableError(self.status)
        now = datetime.now(UTC)
        self.status = ReminderStatus.CANCELLED
        self.cancelled_at = now
        self.cancel_reason = reason
        self.updated_at = now

    def next_occurrence(self) -> datetime | None:
        """Calculate the next scheduled_at for a recurring reminder."""
        if not self.is_recurring or self.recurrence_interval_days is None:
            return None
        from datetime import timedelta

        next_at = self.scheduled_at + timedelta(days=self.recurrence_interval_days)
        if self.recurrence_end_date and next_at > self.recurrence_end_date:
            return None
        return next_at
