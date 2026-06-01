import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DealStage = Literal[
    "new_lead", "qualified", "proposal_sent",
    "in_negotiation", "active", "completed_and_billed", "lost"
]


class DealResponse(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None = None
    title: str
    stage: DealStage
    source: str | None = None
    estimated_value: float | None = None
    actual_value: float | None = None
    currency: str
    notes: str | None = None
    ai_qualification_score: int | None = None
    ai_qualification_recommendation: Literal["qualify", "pass"] | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealActivityEntryResponse(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    entry_type: str
    description: str
    previous_stage: DealStage | None = None
    new_stage: DealStage | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadQualificationResponse(BaseModel):
    deal_id: uuid.UUID
    score: int
    recommendation: Literal["qualify", "pass"]
    reasoning: str
    generation_id: uuid.UUID
