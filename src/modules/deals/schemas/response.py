import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublicIntakeResponse(BaseModel):
    """Minimal confirmation returned to an unauthenticated intake submitter.

    Deliberately excludes owner identity and pipeline internals.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submitted_at: datetime
    message: str = "Thank you — your inquiry has been received."
