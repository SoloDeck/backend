import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    title: str
    stage: str
    source: str | None
    estimated_value: Decimal | None
    actual_value: Decimal | None
    currency: str
    notes: str | None
    desired_timeline: str | None
    project_type: str | None
    service_category: str | None
    pricing_tier: str | None
    # Profession-specific qualification
    profession: str | None = None
    profession_fields: dict[str, Any] | None = None

    ai_qualification_score: int | None
    ai_qualification_recommendation: str | None
    ai_qualification_reasoning: str | None
    ai_qualification_project_type: str | None
    ai_qualification_budget_signal: str | None
    ai_qualification_timeline_signal: str | None
    ai_qualification_urgency_signal: str | None
    ai_qualification_red_flags: list[str] | None
    ai_qualification_detected_signals: list[dict] | None
    ai_qualification_suggested_actions: list[str] | None
    ai_qualification_next_step: str | None
    ai_qualification_price_range_min: int | None
    ai_qualification_price_range_max: int | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_level(self) -> str | None:
        if self.ai_qualification_score is None:
            return None
        if self.ai_qualification_score >= 80:
            return "hot"
        if self.ai_qualification_score >= 50:
            return "warm"
        return "cold"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_ai_qualified(self) -> bool:
        return self.ai_qualification_score is not None and self.ai_qualification_score >= 60


class IntakeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    inquiry_text: str
    estimated_budget: str | None
    desired_timeline: str | None
    source: str | None
    submitted_at: datetime
    created_at: datetime


class PublicIntakeResponse(BaseModel):
    """Minimal confirmation returned to an unauthenticated intake submitter.

    Deliberately excludes owner identity and pipeline internals.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submitted_at: datetime
    message: str = "Thank you — your inquiry has been received."
