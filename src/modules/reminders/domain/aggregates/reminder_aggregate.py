import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.shared.domain.base import DomainEvent
from src.modules.reminders.domain.entities.reminder import Reminder, ReminderType
from src.modules.reminders.domain.entities.delivery_record import DeliveryRecord, DeliveryOutcome
from src.modules.reminders.domain.value_objects.reminder_target import (
    ReminderTarget,
    ReminderTargetType,
)
from src.modules.reminders.domain.value_objects.reminder_status import ReminderStatus
from src.modules.reminders.domain.events.reminder_events import (
    ReminderScheduledEvent,
    ReminderDeliveredEvent,
    ReminderFailedEvent,
    ReminderCancelledEvent,
)


@dataclass
class ReminderAggregate:
    reminder: Reminder
    delivery_records: list[DeliveryRecord] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def schedule(
        cls,
        owner_user_id: uuid.UUID,
        target_type: ReminderTargetType,
        target_id: uuid.UUID,
        reminder_type: ReminderType,
        channel: str,
        message: str,
        scheduled_at: datetime,
        is_recurring: bool = False,
        recurrence_interval_days: int | None = None,
        recurrence_end_date: datetime | None = None,
    ) -> "ReminderAggregate":
        now = datetime.now(timezone.utc)
        reminder_id = uuid.uuid4()
        reminder = Reminder(
            id=reminder_id,
            owner_user_id=owner_user_id,
            target=ReminderTarget(target_type=target_type, target_id=target_id),
            reminder_type=reminder_type,
            channel=channel,
            message=message,
            scheduled_at=scheduled_at,
            status=ReminderStatus.PENDING,
            is_recurring=is_recurring,
            recurrence_interval_days=recurrence_interval_days,
            recurrence_end_date=recurrence_end_date,
            sent_at=None,
            cancelled_at=None,
            cancel_reason=None,
            created_at=now,
            updated_at=now,
        )
        agg = cls(reminder=reminder)
        agg._pending_events.append(
            ReminderScheduledEvent(
                event_id=uuid.uuid4(),
                aggregate_id=reminder_id,
                occurred_at=now,
                owner_user_id=owner_user_id,
                target_type=target_type,
                target_id=target_id,
                scheduled_at=scheduled_at,
            )
        )
        return agg

    def deliver(self, channel: str) -> DeliveryRecord:
        self.reminder.mark_sent()
        record = DeliveryRecord(
            id=uuid.uuid4(),
            reminder_id=self.reminder.id,
            channel=channel,
            outcome=DeliveryOutcome.SUCCESS,
            sent_at=self.reminder.sent_at,  # type: ignore[arg-type]
            error_message=None,
        )
        self.delivery_records.append(record)
        self._pending_events.append(
            ReminderDeliveredEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.reminder.id,
                occurred_at=self.reminder.sent_at,  # type: ignore[arg-type]
                target_type=self.reminder.target.target_type,
                target_id=self.reminder.target.target_id,
                channel=channel,
            )
        )
        return record

    def fail_delivery(self, channel: str, error: str | None = None) -> DeliveryRecord:
        self.reminder.mark_failed()
        now = datetime.now(timezone.utc)
        record = DeliveryRecord(
            id=uuid.uuid4(),
            reminder_id=self.reminder.id,
            channel=channel,
            outcome=DeliveryOutcome.FAILURE,
            sent_at=now,
            error_message=error,
        )
        self.delivery_records.append(record)
        self._pending_events.append(
            ReminderFailedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.reminder.id,
                occurred_at=now,
                error_message=error,
            )
        )
        return record

    def cancel(self, reason: str | None = None) -> None:
        self.reminder.cancel(reason)
        self._pending_events.append(
            ReminderCancelledEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.reminder.id,
                occurred_at=self.reminder.cancelled_at,  # type: ignore[arg-type]
                reason=reason,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
