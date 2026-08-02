import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CreateProposalRequest(BaseModel):
    """status is deliberately NOT accepted here — every proposal starts as draft.
    Previously this schema let the caller set status directly (default "draft" but
    settable to anything), so a client could create a proposal already "sent" or
    "accepted" and skip every rule transition_status() enforces (pricing must be
    set, payment milestones must sum to 100%, share_token generation, superseding
    an existing sent proposal, etc). Status now only ever changes via /send or
    PATCH .../status."""

    deal_id: uuid.UUID
    content: dict = Field(default_factory=dict)


class UpdateProposalRequest(BaseModel):
    content: dict | None = None


class ProposalStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: sent, accepted, rejected, expired")


class ProposalRespondRequest(BaseModel):
    """Client's accept/reject decision, submitted via the public share link."""

    decision: Literal["accepted", "rejected"]
    note: str | None = None


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
