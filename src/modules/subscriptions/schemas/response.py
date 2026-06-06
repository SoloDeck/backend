import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PlanResponse(BaseModel):
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


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    plan_slug: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
