import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    phone: str | None
    avatar_url: str | None
    created_at: datetime


class MessageResponse(BaseModel):
    detail: str
