from datetime import datetime

from pydantic import BaseModel, Field

from src.modules.tasks.domain.value_objects.priority import Priority
from src.modules.tasks.domain.value_objects.task_status import TaskStatus


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    priority: Priority | None = None
    deadline: datetime | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None
    deadline: datetime | None = None


class CreateChecklistItemRequest(BaseModel):
    text: str = Field(min_length=1)
    position: int = 0


class UpdateChecklistItemRequest(BaseModel):
    text: str | None = None
    is_done: bool | None = None
    position: int | None = None
