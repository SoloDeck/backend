from src.modules.reminders.domain.value_objects.reminder_status import ReminderStatus


class ReminderDomainError(Exception):
    """Base for all Reminder domain errors."""


class TerminalReminderError(ReminderDomainError):
    def __init__(self, status: ReminderStatus) -> None:
        super().__init__(f"Reminder is in terminal status '{status.value}'")


class ReminderNotCancellableError(ReminderDomainError):
    def __init__(self, status: ReminderStatus) -> None:
        super().__init__(
            f"Reminder in status '{status.value}' cannot be cancelled"
        )
