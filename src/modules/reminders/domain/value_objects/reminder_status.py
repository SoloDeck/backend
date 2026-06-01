from enum import Enum


class ReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


TERMINAL_REMINDER_STATUSES: frozenset[ReminderStatus] = frozenset(
    {ReminderStatus.CANCELLED, ReminderStatus.SENT}
)
