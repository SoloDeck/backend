import uuid
from datetime import datetime
from decimal import Decimal

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
    project_type: str | None
    service_category: str | None
    pricing_tier: str | None
    ai_qualification_score: int | None
    ai_qualification_recommendation: str | None
    ai_qualification_reasoning: str | None
    ai_qualification_project_type: str | None
    ai_qualification_budget_signal: str | None
    ai_qualification_timeline_signal: str | None
    ai_qualification_urgency_signal: str | None
    ai_qualification_red_flags: list[str] | None
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
