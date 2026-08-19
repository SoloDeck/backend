import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ProposalRequest(BaseModel):
    deal_id: uuid.UUID
    content: dict
    # CỐ Ý khoá về đúng "draft". Trước đây đây là `str` tự do và `create()` ghi thẳng vào DB, nên
    # `POST /proposals {"status": "accepted"}` tạo ngay một báo giá ĐÃ CHẤP NHẬN — bỏ qua toàn bộ
    # `transition_status`: cổng chưa-chốt-giá, cổng hạng mục 0đ, cổng tổng-lệch-giá-chào và cả
    # bảng chuyển trạng thái hợp lệ. Từ đó tạo hợp đồng được luôn.
    #
    # Mọi chuyển trạng thái phải đi qua `PATCH /proposals/{id}/status`, nơi các cổng đó sống.
    # Siết bây giờ vì đường tạo thủ công vừa trở thành lối đi CHÍNH, không còn là ngách.  #Huynh
    status: Literal["draft"] = "draft"


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
    # Mẫu điều khoản freelancer chọn (từ thư viện admin). None = "AI tự viết", không mẫu.
    template_id: uuid.UUID | None = None


class ProposalPriceRequest(BaseModel):
    """Freelancer CHỐT giá cuối cùng cho bản báo giá.

    Bộ định giá chỉ đưa ra một KHOẢNG kèm cách suy ra. Con số gửi cho khách phải do CON
    NGƯỜI quyết — đó là ranh giới đạo đức của cả tính năng: AI hỗ trợ, không thay mặt.

    Cố ý KHÔNG chặn giá nằm ngoài khoảng đề xuất. Freelancer biết những điều hệ thống không
    biết (khách quen, muốn lấy dự án làm portfolio, đang cần việc gấp). Ngoài khoảng thì
    CẢNH BÁO, không CẤM.  #Huynh
    """

    price: Decimal = Field(gt=0, description="Giá chào cuối cùng, VND")
