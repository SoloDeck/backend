import uuid

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    deal_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    note: str | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    note: str | None = None
    is_done: bool | None = None
