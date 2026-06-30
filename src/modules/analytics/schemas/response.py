import uuid
from decimal import Decimal

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    total_clients: int
    active_deals: int
    total_revenue: Decimal
    pending_invoices: int


class RevenueResponse(BaseModel):
    total_invoiced: Decimal
    total_collected: Decimal
    total_outstanding: Decimal


class PipelineStageResponse(BaseModel):
    stage: str
    deal_count: int
    total_value: Decimal


class WinRateResponse(BaseModel):
    won: int
    lost: int
    win_rate: float


class TopClientResponse(BaseModel):
    client_id: uuid.UUID
    name: str
    revenue: Decimal


class AiUsageResponse(BaseModel):
    generations_used: int
    estimated_cost_usd: Decimal
