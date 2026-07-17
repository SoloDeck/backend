import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class ProposalRequest(BaseModel):
    deal_id: uuid.UUID
    content: dict
    status: str = "draft"


class ProposalStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: sent, accepted, rejected, expired")


class AiProposalRequest(BaseModel):
    deal_id: uuid.UUID
    client_name: str
    company_name: str | None = None
    project_type: str
    project_description: str
    estimated_scope: str | None = None
    budget: str | None = None
    urgency: str | None = None
    service_category: str
    pricing_tier: str
    freelancer_name: str


class ProposalPriceRequest(BaseModel):
    """Freelancer CHỐT giá cuối cùng cho bản báo giá.

    Bộ định giá chỉ đưa ra một KHOẢNG kèm cách suy ra. Con số gửi cho khách phải do CON
    NGƯỜI quyết — đó là ranh giới đạo đức của cả tính năng: AI hỗ trợ, không thay mặt.

    Cố ý KHÔNG chặn giá nằm ngoài khoảng đề xuất. Freelancer biết những điều hệ thống không
    biết (khách quen, muốn lấy dự án làm portfolio, đang cần việc gấp). Ngoài khoảng thì
    CẢNH BÁO, không CẤM.  #Huynh
    """

    price: Decimal = Field(gt=0, description="Giá chào cuối cùng, VND")
