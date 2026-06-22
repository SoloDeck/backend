import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DealTaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    note: str | None = None


class DealTaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    note: str | None = None
    is_done: bool | None = None


class DealTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID
    title: str
    note: str | None
    is_done: bool
    created_at: datetime
    updated_at: datetime


class DealTaskListResponse(BaseModel):
    tasks: list[DealTaskResponse]
    total: int
    done: int
    percent: int
