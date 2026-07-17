import uuid
from datetime import datetime
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
    """Lượt dùng AI trong kỳ thanh toán hiện tại.

    `generations_used` + `estimated_cost_usd` là hai trường BẮT BUỘC theo
    contracts/openapi.yaml — giữ nguyên. Mấy trường dưới là THÊM: hợp đồng không khoá
    `additionalProperties` nên thêm là hợp lệ, và không có chúng thì màn "Gói đăng ký"
    chỉ hiện được "đã dùng 3 lượt" mà không biết 3 trên bao nhiêu.  #Huynh
    """

    generations_used: int
    estimated_cost_usd: Decimal

    limit: int = 0
    remaining: int = 0
    can_use_ai: bool = False
    period_start: datetime | None = None
    period_end: datetime | None = None
