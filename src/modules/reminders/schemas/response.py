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


class ReminderDeliveryResponse(BaseModel):
    """Kết quả bấm "Gửi ngay".

    Trả kèm `detail` — một câu tiếng Việt hiện thẳng lên toast — thay vì bắt frontend tự
    đoán nghĩa của `status`. Lý do hỏng ("khách chưa có email") chỉ backend mới biết.
    """

    reminder: ReminderResponse
    status: str
    detail: str
    delivered: bool
