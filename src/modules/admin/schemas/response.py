import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    phone: str | None
    created_at: datetime


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
