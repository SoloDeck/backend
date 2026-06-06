import uuid
from datetime import datetime

from pydantic import BaseModel


class ReminderRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    reminder_type: str
    channel: str
    scheduled_at: datetime
    message_preview: str | None = None
