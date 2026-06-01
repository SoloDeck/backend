import uuid
from typing import Literal

from pydantic import BaseModel, Field

DealStage = Literal[
    "new_lead", "qualified", "proposal_sent",
    "in_negotiation", "active", "completed_and_billed", "lost"
]
DealSource = Literal["inbound", "referral", "outreach", "platform", "other"]


class CreateDealRequest(BaseModel):
    client_id: uuid.UUID
    title: str = Field(max_length=500)
    source: DealSource | None = None
    estimated_value: float | None = Field(default=None, ge=0)
    currency: str = "VND"
    notes: str | None = None


class UpdateDealRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    source: DealSource | None = None
    estimated_value: float | None = Field(default=None, ge=0)
    actual_value: float | None = Field(default=None, ge=0)
    currency: str | None = None
    notes: str | None = None


class StageTransitionRequest(BaseModel):
    target_stage: DealStage
    note: str | None = None


class AddNoteRequest(BaseModel):
    description: str
