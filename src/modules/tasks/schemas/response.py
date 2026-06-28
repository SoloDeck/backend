import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.modules.tasks.domain.value_objects.priority import Priority
from src.modules.tasks.domain.value_objects.task_owner import TaskOwner
from src.modules.tasks.domain.value_objects.task_status import TaskStatus


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    text: str
    is_done: bool
    position: int


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: TaskOwner
    entity_id: uuid.UUID
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus
    deadline: datetime | None
    checklist_items: list[ChecklistItemResponse] = []
    created_at: datetime
    updated_at: datetime
