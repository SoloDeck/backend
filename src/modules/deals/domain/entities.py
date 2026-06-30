"""Deals domain — Deal aggregate root."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

DealStage = Literal[
    "new_lead",
    "qualified",
    "proposal_sent",
    "in_negotiation",
    "active",
    "completed_and_billed",
    "lost",
]
DealSource = Literal["inbound", "referral", "outreach", "platform", "other"]
DealActivityType = Literal["stage_change", "note_added", "document_attached", "ai_qualification"]

STAGE_TRANSITIONS: dict[str, list[str]] = {
    "new_lead": ["qualified", "lost"],
    "qualified": ["proposal_sent", "lost"],
    "proposal_sent": ["in_negotiation", "lost"],
    "in_negotiation": ["active", "lost"],
    "active": ["completed_and_billed", "lost"],
    "completed_and_billed": [],
    "lost": [],
}
TERMINAL_STAGES = {"completed_and_billed", "lost"}


@dataclass
class DealActivityEntry:
    id: uuid.UUID
    deal_id: uuid.UUID
    entry_type: DealActivityType
    description: str
    previous_stage: DealStage | None
    new_stage: DealStage | None
    created_at: datetime


@dataclass
class Deal:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    title: str
    stage: DealStage
    currency: str
    source: DealSource | None = None
    estimated_value: float | None = None
    actual_value: float | None = None
    notes: str | None = None
    ai_qualification_score: int | None = None
    ai_qualification_recommendation: Literal["qualify", "pass"] | None = None
    closed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    deleted_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES

    def can_transition_to(self, target: str) -> bool:
        return target in STAGE_TRANSITIONS.get(self.stage, [])
