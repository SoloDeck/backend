from enum import StrEnum


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


TERMINAL_REMINDER_STATUSES: frozenset[ReminderStatus] = frozenset(
    {ReminderStatus.CANCELLED, ReminderStatus.SENT}
)
