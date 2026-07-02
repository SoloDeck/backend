from decimal import Decimal

from pydantic import BaseModel


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None


class FreelancerProfileUpdateRequest(BaseModel):
    professional_title: str | None = None
    bio: str | None = None
    skills: list[str] | None = None
    service_categories: list[str] | None = None
    avatar_url: str | None = None
    portfolio_url: str | None = None
    is_listed: bool | None = None


class UpdateProfessionalProfileRequest(BaseModel):
    skills: list[str] | None = None
    specialization: str | None = None
    default_hourly_rate: Decimal | None = None
    currency: str | None = None
    portfolio_url: str | None = None
    business_name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
