import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    type: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CommLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    channel: str
    summary: str
    communicated_at: datetime
    created_at: datetime


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    tag: str
    created_at: datetime


class MessageResponse(BaseModel):
    detail: str
