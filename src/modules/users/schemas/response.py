import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class ProfessionalProfileDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skills: list[str] | None = None
    specialization: str | None = None
    default_hourly_rate: Decimal | None = None
    currency: str
    portfolio_url: str | None = None
    business_name: str | None = None


class PreferencesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    locale: str
    timezone: str
    notification_channel: str
    theme: str


def build_user_fields(obj: Any) -> dict[str, Any]:
    """Map a UserModel ORM instance onto the UserResponse field shape."""
    return {
        "id": obj.id,
        "email": obj.email,
        "full_name": obj.full_name,
        "role": obj.role,
        "status": obj.status,
        "phone": obj.phone,
        "avatar_url": obj.avatar_url,
        "bio": obj.bio,
        "intake_share_token": obj.intake_share_token,
        "professional_profile": obj,
        "preferences": obj,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
    }


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    phone: str | None
    avatar_url: str | None
    bio: str | None
    intake_share_token: str | None
    professional_profile: ProfessionalProfileDTO
    preferences: PreferencesDTO
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _nest_profile_and_preferences(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        return build_user_fields(obj)


class MessageResponse(BaseModel):
    detail: str
