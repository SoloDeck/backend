from pydantic import BaseModel


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    phone: str | None = None


class FreelancerProfileUpdateRequest(BaseModel):
    professional_title: str | None = None
    bio: str | None = None
    skills: list[str] | None = None
    service_categories: list[str] | None = None
    avatar_url: str | None = None
    portfolio_url: str | None = None
    is_listed: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
