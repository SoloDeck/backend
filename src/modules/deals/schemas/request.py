import uuid
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


class DealRequest(BaseModel):
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
    # Profession-specific intake answers (5 questions for the selected profession)
    profession_fields: dict[str, Any] | None = None
