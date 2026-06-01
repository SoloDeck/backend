"""Deal — entity holding core deal state.

The Deal object is the aggregate root entity. All mutation goes through
DealAggregate, which calls methods here and collects child objects.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.modules.deals.domain.value_objects.deal_stage import (
    DealStage,
    STAGE_TRANSITIONS,
    TERMINAL_STAGES,
)
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence
from src.shared.domain.value_objects.money import Money


@dataclass
class Deal:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_id: uuid.UUID            # immutable after creation
    title: str
    stage: DealStage
    value: Money | None
    source: str | None
    expected_close_date: datetime | None
    ai_score: int | None
    ai_confidence: AIConfidence | None
    ai_recommendation: str | None   # "qualify" | "pass" | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES

    @property
    def is_won(self) -> bool:
        return self.stage == DealStage.COMPLETED_AND_BILLED

    @property
    def is_lost(self) -> bool:
        return self.stage == DealStage.LOST

    def can_transition_to(self, target: DealStage) -> bool:
        return target in STAGE_TRANSITIONS[self.stage]

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def apply_stage_transition(self, target: DealStage) -> None:
        """Mutate stage. Caller must validate via can_transition_to first."""
        self.stage = target
        self.updated_at = datetime.now(timezone.utc)
        if target in TERMINAL_STAGES:
            self.closed_at = datetime.now(timezone.utc)

    def apply_lead_score(
        self, score: int, confidence: AIConfidence, recommendation: str
    ) -> None:
        self.ai_score = score
        self.ai_confidence = confidence
        self.ai_recommendation = recommendation
        self.updated_at = datetime.now(timezone.utc)

    def update_title(self, title: str) -> None:
        if not title.strip():
            raise ValueError("Deal title must not be blank")
        self.title = title.strip()
        self.updated_at = datetime.now(timezone.utc)

    def update_value(self, value: Money) -> None:
        self.value = value
        self.updated_at = datetime.now(timezone.utc)

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
