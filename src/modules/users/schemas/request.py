from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Literal


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    avatar_url: HttpUrl | None = None
    bio: str | None = None
    phone: str | None = None


class UpdateProfessionalProfileRequest(BaseModel):
    skills: list[str] | None = None
    specialization: str | None = None
    default_hourly_rate: float | None = None
    currency: str | None = None
    portfolio_url: HttpUrl | None = None
    business_name: str | None = None


class UpdatePreferencesRequest(BaseModel):
    locale: str | None = None
    timezone: str | None = None
    notification_channel: Literal["email", "in_app", "both"] | None = None
    theme: Literal["light", "dark"] | None = None
