"""Project — pure domain entity.

No I/O, no SQLAlchemy. Mirrors the layered-architecture rule that domain
entities are plain Python dataclasses holding business state and invariants.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from src.modules.projects.domain.value_objects.project_status import ProjectStatus


@dataclass
class Project:
    id: uuid.UUID
    owner_id: uuid.UUID
    deal_id: uuid.UUID | None
    name: str
    description: str | None
    start_date: date | None
    end_date: date | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    def rename(self, name: str) -> None:
        if not name.strip():
            raise ValueError("Project name must not be blank")
        self.name = name.strip()
