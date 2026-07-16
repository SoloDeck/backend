import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from src.modules.users.schemas.response import UserResponse, build_user_fields

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int
    page_size: int


class AdminPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    price_monthly: Decimal
    currency: str
    can_use_ai: bool
    can_export_pdf: bool
    max_clients: int | None
    max_deals: int | None
    max_ai_generations_per_month: int
    is_active: bool
    created_at: datetime


class AdminSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    plan_slug: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None
    override_expires_at: datetime | None
    created_at: datetime


def _build_subscription_fields(sub: Any) -> dict[str, Any]:
    return {
        "id": sub.id,
        "user_id": sub.user_id,
        "plan_id": sub.plan_id,
        "plan_name": sub.plan.name,
        "plan_slug": sub.plan.slug,
        "status": sub.status,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "cancelled_at": sub.cancelled_at,
        "override_expires_at": sub.override_expires_at,
        "created_at": sub.created_at,
    }


class AdminUserResponse(UserResponse):
    deleted_at: datetime | None = None
    subscription: AdminSubscriptionResponse | None = None

    @model_validator(mode="before")
    @classmethod
    def _nest_and_add_deleted_at(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj
        subscription = _build_subscription_fields(obj.subscription) if obj.subscription else None
        return {
            **build_user_fields(obj),
            "deleted_at": obj.deleted_at,
            "subscription": subscription,
        }


class AdminAiCostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    ai_module: str
    model_used: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    status: str
    occurred_at: datetime


class AdminAiCostTotals(BaseModel):
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


class AdminAiCostPagedResponse(BaseModel):
    data: list[AdminAiCostResponse]
    total: int
    page: int
    page_size: int
    totals: AdminAiCostTotals


class AdminAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    actor_user_id: uuid.UUID | None
    target_type: str | None
    target_id: uuid.UUID | None
    description: str
    occurred_at: datetime


class AdminTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_type: str
    name: str
    content: dict
    plan_tier_required: str | None
    version_number: int
    is_active: bool
    created_by_admin_id: uuid.UUID
    created_at: datetime


class AdminFeatureFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flag_name: str
    is_enabled: bool
    rollout_percentage: int
    target_user_ids: list[uuid.UUID] | None
    description: str | None
    created_at: datetime


class AdminPlatformMetricsResponse(BaseModel):
    total_users: int
    active_users: int
    suspended_users: int
    total_subscriptions: int
    active_subscriptions: int
    total_plans: int
    active_plans: int
    total_deals: int
    total_clients: int
    ai_cost_last_30_days: Decimal
