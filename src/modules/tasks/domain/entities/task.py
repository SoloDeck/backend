"""Task — pure domain entity.

Polymorphic: a task is bound to an owning entity by (entity_type, entity_id)
with no FK constraint, mirroring the reminders module's target_type/target_id.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src.modules.tasks.domain.entities.checklist_item import ChecklistItem
from src.modules.tasks.domain.value_objects.priority import Priority
from src.modules.tasks.domain.value_objects.task_owner import TaskOwner
from src.modules.tasks.domain.value_objects.task_status import TaskStatus


@dataclass
class Task:
    id: uuid.UUID
    entity_type: TaskOwner
    entity_id: uuid.UUID
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
    checklist_items: list[ChecklistItem] = field(default_factory=list)
