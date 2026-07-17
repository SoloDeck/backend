import uuid
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field

from src.modules.deals.domain.value_objects.deal_stage import DealStage


class DealRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "client_id": "e1f881a5-fe2a-4f62-bcda-c0371077a924",
                "title": "Xay dung website ban hang",
                "stage": "new_lead",
                "source": "referral",
                "project_type": "E-commerce Website",
                "service_category": "Web Development",
                "pricing_tier": "standard",
                "estimated_value": 50000000,
                "currency": "VND",
                "desired_timeline": "2 thang",
                "notes": "Khach can website ban hang tich hop thanh toan VNPay va MOMO",
            }
        }
    }

    client_id: uuid.UUID
    title: str
    stage: str = "new_lead"
    source: str | None = None
    # ge=0: trước đây tạo được deal giá trị ÂM (-1.000.000 đ) và nó cộng luôn vào tổng
    # doanh thu trên bảng Kanban. API trả 201 vô tư.  #Huynh
    estimated_value: Decimal | None = Field(default=None, ge=0)
    actual_value: Decimal | None = Field(default=None, ge=0)
    currency: str = "VND"
    notes: str | None = None
    desired_timeline: str | None = None
    project_type: str | None = None
    service_category: str | None = None
    pricing_tier: str | None = None


class DealStageRequest(BaseModel):
    # Kiểu là DealStage (enum) chứ không phải str trần: giai đoạn rác ("khong_ton_tai")
    # trước đây lọt qua schema rồi mới bị service chặn, nên trả 409 CONFLICT — sai ngữ
    # nghĩa. 409 nghĩa là "xung đột trạng thái", còn đây là DỮ LIỆU KHÔNG HỢP LỆ → 422.
    # Để pydantic chặn ngay ở cửa, FastAPI tự trả 422 kèm danh sách giá trị hợp lệ.  #Huynh
    target_stage: DealStage = Field(validation_alias=AliasChoices("target_stage", "stage"))

    @property
    def stage(self) -> str:
        return self.target_stage


class PublicIntakeRequest(BaseModel):
    """Body for the public (unauthenticated) lead intake form.

    Required fields are validated dynamically against the freelancer's form config.
    `name` is always required at the schema level (needed to create a client record).
    """

    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    project_name: str | None = Field(default=None, max_length=500)
    inquiry_text: str | None = Field(default=None, max_length=5000)
    estimated_budget: str | None = Field(default=None, max_length=255)
    desired_timeline: str | None = Field(default=None, max_length=255)
