import uuid
from decimal import Decimal

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
    project_type: str | None = None
    service_category: str | None = None
    pricing_tier: str | None = None


class DealStageRequest(BaseModel):
    target_stage: str = Field(validation_alias=AliasChoices("target_stage", "stage"))

    @property
    def stage(self) -> str:
        return self.target_stage


class PublicIntakeRequest(BaseModel):
    """Body for the public (unauthenticated) lead intake form.

    `name` and `inquiry_text` are required; an empty body fails validation (422).
    `inquiry_text` is length-capped so an oversized body is rejected (422) rather
    than persisted.
    """

    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    inquiry_text: str = Field(min_length=1, max_length=5000)
    estimated_budget: str | None = Field(default=None, max_length=255)
    desired_timeline: str | None = Field(default=None, max_length=255)
