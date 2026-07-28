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
    """Tiền của freelancer, nhìn từ HAI nguồn khác nhau — cố ý không gộp.

    `total_invoiced/collected/outstanding` là tiền theo **hoá đơn** (chứng từ đã xuất). Giữ
    nguyên ngữ nghĩa cũ: đổi ngầm ý nghĩa một trường đang có là nơi khác đọc sai mà không ai
    biết.

    `contracted/milestone_*` là tiền theo **mốc thanh toán của hợp đồng đã ký** — nguồn
    chính của bảng doanh thu từ Phase B, vì luồng hoàn thành dự án đo bằng task "Thu tiền:"
    chứ không đòi hoá đơn nữa.  #Huynh
    """

    total_invoiced: Decimal
    total_collected: Decimal
    total_outstanding: Decimal
    # --- Theo mốc thanh toán (nguồn chính của bảng doanh thu) ---
    total_contracted: Decimal = Decimal(0)
    milestone_collected: Decimal = Decimal(0)
    milestone_outstanding: Decimal = Decimal(0)
    milestones_pending: int = 0


class PipelineStageResponse(BaseModel):
    stage: str
    deal_count: int
    total_value: Decimal


class MonthlyRevenueResponse(BaseModel):
    """Một tháng trên biểu đồ doanh thu.

    `month` là "YYYY-MM". Chuỗi trả về LIỀN MẠCH — tháng không có hoá đơn vẫn xuất hiện
    với số 0, để biểu đồ ở frontend không bị đứt cột giữa chừng và trục tháng thẳng hàng.
    """

    month: str
    invoiced: Decimal
    collected: Decimal


class WinRateResponse(BaseModel):
    won: int
    lost: int
    win_rate: float


class TopClientResponse(BaseModel):
    client_id: uuid.UUID
    name: str
    revenue: Decimal
    # Khách này còn nợ bao nhiêu + bao nhiêu dự án — "ai mang lại nhiều tiền nhất" mà không
    # kèm "ai còn nợ nhiều nhất" thì mới kể được nửa câu chuyện.
    outstanding: Decimal = Decimal(0)
    deal_count: int = 0


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
