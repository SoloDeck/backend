import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reminder_type: str
    channel: str
    status: str
    scheduled_at: datetime
    message_preview: str | None
    created_at: datetime
    updated_at: datetime
