import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FreelancerCategoryResponse(BaseModel):
    slug: str
    name: str
    sub_skills: str


class FreelancerPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    professional_title: str | None
    bio: str | None
    avatar_url: str | None
    skills: list[str]
    service_categories: list[str]
    portfolio_url: str | None
    rating_average: float | None
    rating_count: int
    completed_project_count: int
    is_new: bool
    created_at: datetime
