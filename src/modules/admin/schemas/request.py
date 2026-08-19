import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field

from src.ai.shared.constants import LLMProviderName

# Ràng buộc HÌNH DẠNG, khớp đúng cột `subscription_plans.price_monthly NUMERIC(10, 2)`
# (infrastructure/database/models.py). Không có nó thì `price_monthly: -5` hay
# `99999999999` đi thẳng xuống Postgres và nổ thành 500 trần, thay vì 422 nói được sai gì.
#
# Ràng buộc NGHIỆP VỤ (khoảng tiền MoMo nhận) KHÔNG nằm ở đây — nó đọc từ Settings nên
# không đặt được vào `Field()`, và nó thuộc về tầng service. Xem `AdminService`.
PlanPrice = Annotated[Decimal, Field(ge=0, le=Decimal("99999999.99"), decimal_places=2)]


class AdminUpdateUserRequest(BaseModel):
    role: Literal["freelancer", "admin"] | None = None
    status: Literal["active", "suspended", "deleted"] | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None


class AdminPlanRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=50)
    price_monthly: PlanPrice
    # SoloDesk bán cho freelancer Việt và thu qua MoMo — MoMo chỉ thanh toán VND.
    #
    # Trước đây field này là `str = "USD"`: giao diện quản trị hardcode "VND" nên tạo qua
    # UI thì không sao, nhưng tạo qua API mà quên truyền là ra một gói USD KHÔNG BAO GIỜ
    # mua được — chết mãi tận `_to_whole_vnd`, cách chỗ gây lỗi bốn tầng.  #Huynh
    currency: Literal["VND"] = "VND"
    can_use_ai: bool = False
    can_export_pdf: bool = False
    max_clients: int | None = Field(default=None, ge=0)
    max_deals: int | None = Field(default=None, ge=0)
    max_ai_generations_per_month: int = Field(default=0, ge=0)


class AdminUpdatePlanRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=50)
    price_monthly: PlanPrice | None = None
    currency: Literal["VND"] | None = None
    can_use_ai: bool | None = None
    can_export_pdf: bool | None = None
    max_clients: int | None = Field(default=None, ge=0)
    max_deals: int | None = Field(default=None, ge=0)
    max_ai_generations_per_month: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AdminSubscriptionOverrideRequest(BaseModel):
    plan_id: uuid.UUID | None = None
    override_expires_at: datetime | None = None


class AdminCreateTemplateRequest(BaseModel):
    name: str
    template_type: Literal["proposal", "contract"]
    # Slug nghề (intake_form/professions.py) hoặc None = mẫu dùng chung. Service validate
    # qua seam professions, sai slug → 422.
    profession: str | None = None
    content: dict
    plan_tier_required: str | None = None
    is_active: bool = False


class AdminUpdateTemplateRequest(BaseModel):
    name: str | None = None
    profession: str | None = None
    content: dict | None = None
    is_active: bool | None = None
    plan_tier_required: str | None = None


class AdminUpdateFeatureFlagRequest(BaseModel):
    is_enabled: bool | None = None
    rollout_percentage: int | None = Field(default=None, ge=0, le=100)
    target_user_ids: list[uuid.UUID] | None = None
    description: str | None = None


class AdminUpdateLLMProviderRequest(BaseModel):
    # Dùng chung LLMProviderName với get_llm_provider() để danh sách nhà cung
    # cấp chỉ tồn tại ở MỘT nơi (src/ai/shared/constants.py). Chính bản Literal
    # viết tay ở đây từng làm "ollama" không chọn được dù mọi tầng dưới đã hỗ trợ.
    llm_provider: LLMProviderName
    llm_model: str
