import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class AdminUpdateUserRequest(BaseModel):
    role: Literal["freelancer", "admin"] | None = None
    status: Literal["active", "suspended", "deleted"] | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class AdminPlanRequest(BaseModel):
    name: str
    slug: str
    price_monthly: Decimal
    currency: str = "USD"
    can_use_ai: bool = False
    can_export_pdf: bool = False
    max_clients: int | None = None
    max_deals: int | None = None
    max_ai_generations_per_month: int = 0


class AdminUpdatePlanRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    price_monthly: Decimal | None = None
    currency: str | None = None
    can_use_ai: bool | None = None
    can_export_pdf: bool | None = None
    max_clients: int | None = None
    max_deals: int | None = None
    max_ai_generations_per_month: int | None = None
    is_active: bool | None = None


class AdminSubscriptionOverrideRequest(BaseModel):
    plan_id: uuid.UUID | None = None
    override_expires_at: datetime | None = None


class AdminCreateTemplateRequest(BaseModel):
    name: str
    template_type: Literal["proposal", "contract"]
    content: dict
    plan_tier_required: str | None = None
    is_active: bool = False


class AdminUpdateTemplateRequest(BaseModel):
    name: str | None = None
    content: dict | None = None
    is_active: bool | None = None
    plan_tier_required: str | None = None


class AdminUpdateFeatureFlagRequest(BaseModel):
    is_enabled: bool | None = None
    rollout_percentage: int | None = Field(default=None, ge=0, le=100)
    target_user_ids: list[uuid.UUID] | None = None
    description: str | None = None
