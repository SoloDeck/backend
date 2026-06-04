from decimal import Decimal

from pydantic import BaseModel


class AdminUpdateUserRequest(BaseModel):
    role: str | None = None
    status: str | None = None
    full_name: str | None = None


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
    is_active: bool = True
