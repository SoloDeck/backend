import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from src.modules.projects.domain.value_objects.project_status import ProjectStatus


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_id: uuid.UUID | None
    owner_id: uuid.UUID
    name: str
    description: str | None
    start_date: date | None
    end_date: date | None
    status: ProjectStatus
    task_count: int = 0
    done_count: int = 0
    created_at: datetime
    updated_at: datetime
