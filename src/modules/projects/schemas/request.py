import uuid
from datetime import date

from pydantic import BaseModel, Field

from src.modules.projects.domain.value_objects.project_status import ProjectStatus


class CreateProjectRequest(BaseModel):
    deal_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None
