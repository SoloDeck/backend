import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProfessionalProfileResponse(BaseModel):
    skills: list[str]
    specialization: str | None
    default_hourly_rate: float | None
    currency: str
    portfolio_url: str | None
    business_name: str | None


class PreferencesResponse(BaseModel):
    locale: str
    timezone: str
    notification_channel: Literal["email", "in_app", "both"]
    theme: Literal["light", "dark"]


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["freelancer", "admin"]
    status: Literal["active", "suspended", "deleted"]
    avatar_url: str | None
    bio: str | None
    phone: str | None
    professional_profile: ProfessionalProfileResponse
    preferences: PreferencesResponse
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
