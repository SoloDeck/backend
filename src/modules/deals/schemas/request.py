import uuid
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


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
    estimated_value: Decimal | None = None
    actual_value: Decimal | None = None
    currency: str = "VND"
    notes: str | None = None
    desired_timeline: str | None = None
    project_type: str | None = None
    service_category: str | None = None
    pricing_tier: str | None = None
    # Profession-specific qualification
    profession: str | None = None
    profession_fields: dict[str, Any] | None = None


class DealStageRequest(BaseModel):
    target_stage: str = Field(validation_alias=AliasChoices("target_stage", "stage"))

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
    # Profession selected by the client
    profession: str | None = None
    # Profession-specific intake answers
    qualification_fields: dict[str, Any] | None = None
