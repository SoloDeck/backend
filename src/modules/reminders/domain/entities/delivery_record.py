import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DeliveryOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class DeliveryRecord:
    """Append-only delivery attempt log for a single reminder."""

    id: uuid.UUID
    reminder_id: uuid.UUID
    channel: str  # "email" | "zalo" | "in_app"
    outcome: DeliveryOutcome
    sent_at: datetime
    error_message: str | None
