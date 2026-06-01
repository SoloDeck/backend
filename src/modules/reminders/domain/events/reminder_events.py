import uuid
from dataclasses import dataclass
from datetime import datetime

from src.shared.domain.base import DomainEvent
from src.modules.reminders.domain.value_objects.reminder_target import ReminderTargetType


@dataclass(frozen=True)
class ReminderScheduledEvent(DomainEvent):
    owner_user_id: uuid.UUID
    target_type: ReminderTargetType
    target_id: uuid.UUID
    scheduled_at: datetime


@dataclass(frozen=True)
class ReminderDeliveredEvent(DomainEvent):
    target_type: ReminderTargetType
    target_id: uuid.UUID
    channel: str


@dataclass(frozen=True)
class ReminderFailedEvent(DomainEvent):
    error_message: str | None


@dataclass(frozen=True)
class ReminderCancelledEvent(DomainEvent):
    reason: str | None
