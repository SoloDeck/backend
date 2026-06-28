"""ChecklistItem — pure domain entity (sub-item of a Task)."""

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChecklistItem:
    id: uuid.UUID
    task_id: uuid.UUID
    text: str
    is_done: bool
    position: int
    created_at: datetime
