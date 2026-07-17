"""Schema trả về cho thông báo."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class UnreadCountResponse(BaseModel):
    """Chỉ con số cho cái chấm đỏ trên chuông — không kéo cả danh sách về."""

    unread_count: int
