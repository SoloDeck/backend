"""Users domain — User aggregate root."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class ProfessionalProfile:
    skills: list[str]
    specialization: str | None
    default_hourly_rate: float | None
    currency: str
    portfolio_url: str | None
    business_name: str | None


@dataclass
class Preferences:
    locale: str
    timezone: str
    notification_channel: Literal["email", "in_app", "both"]
    theme: Literal["light", "dark"]


@dataclass
class User:
    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["freelancer", "admin"]
    status: Literal["active", "suspended", "deleted"]
    avatar_url: str | None
    bio: str | None
    phone: str | None
    professional_profile: ProfessionalProfile
    preferences: Preferences
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
