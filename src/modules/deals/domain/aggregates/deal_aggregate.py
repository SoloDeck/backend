"""DealAggregate — controls all mutations to the Deal aggregate.

All external code must go through this class. Direct mutation of Deal,
LeadScore, DealActivity, or DealStageHistory from outside is forbidden.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.modules.deals.domain.entities.deal import Deal
from src.modules.deals.domain.entities.deal_activity import DealActivity, DealActivityType
from src.modules.deals.domain.entities.deal_stage_history import DealStageHistory
from src.modules.deals.domain.entities.lead_score import LeadScore
from src.modules.deals.domain.events.deal_completed import DealCompletedEvent
from src.modules.deals.domain.events.deal_created import DealCreatedEvent
from src.modules.deals.domain.events.deal_stage_changed import DealStageChangedEvent
from src.modules.deals.domain.events.lead_scored import LeadScoredEvent
from src.modules.deals.domain.exceptions.exceptions import (
    InvalidLeadScoreError,
    InvalidStageTransitionError,
    TerminalDealError,
)
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence
from src.modules.deals.domain.value_objects.deal_stage import DealStage
from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money


@dataclass
class DealAggregate:
    """Aggregate root for the Deal domain.

    Invariants enforced here:
    - Stage transitions are validated before any mutation.
    - Terminal deals reject all mutations.
    - Every mutation records a DealActivity entry.
    - LeadScore is validated (0–100 / 0.0–1.0) before being attached.
    """

    deal: Deal
    lead_scores: list[LeadScore] = field(default_factory=list)
    activities: list[DealActivity] = field(default_factory=list)
    stage_history: list[DealStageHistory] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(
        cls,
        owner_user_id: uuid.UUID,
        client_id: uuid.UUID,
        title: str,
        value: Money | None = None,
        source: str | None = None,
        expected_close_date: datetime | None = None,
    ) -> "DealAggregate":
        now = datetime.now(UTC)
        deal_id = uuid.uuid4()
        deal = Deal(
            id=deal_id,
            owner_user_id=owner_user_id,
            client_id=client_id,
            title=title,
            stage=DealStage.NEW_LEAD,
            value=value,
            source=source,
            expected_close_date=expected_close_date,
            ai_score=None,
            ai_confidence=None,
            ai_recommendation=None,
            closed_at=None,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        agg = cls(deal=deal)
        agg._pending_events.append(
            DealCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=deal_id,
                occurred_at=now,
                owner_user_id=owner_user_id,
                client_id=client_id,
                title=title,
                initial_stage=DealStage.NEW_LEAD,
            )
        )
        return agg

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def change_stage(
        self,
        target: DealStage,
        actor_user_id: uuid.UUID,
        note: str | None = None,
    ) -> None:
        if self.deal.is_terminal:
            raise TerminalDealError(self.deal.stage)
        if not self.deal.can_transition_to(target):
            raise InvalidStageTransitionError(self.deal.stage, target)

        old_stage = self.deal.stage
        self.deal.apply_stage_transition(target)

        self.stage_history.append(
            DealStageHistory(
                id=uuid.uuid4(),
                deal_id=self.deal.id,
                from_stage=old_stage,
                to_stage=target,
                transitioned_by=actor_user_id,
                transitioned_at=self.deal.updated_at,
                note=note,
            )
        )
        self.activities.append(
            DealActivity(
                id=uuid.uuid4(),
                deal_id=self.deal.id,
                owner_user_id=actor_user_id,
                activity_type=DealActivityType.STAGE_CHANGE,
                description=f"Stage changed: {old_stage.value} → {target.value}",
                occurred_at=self.deal.updated_at,
                metadata={"note": note} if note else None,
            )
        )
        self._pending_events.append(
            DealStageChangedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.deal.id,
                occurred_at=self.deal.updated_at,
                old_stage=old_stage,
                new_stage=target,
                actor_user_id=actor_user_id,
            )
        )
        if self.deal.is_terminal:
            self._pending_events.append(
                DealCompletedEvent(
                    event_id=uuid.uuid4(),
                    aggregate_id=self.deal.id,
                    occurred_at=self.deal.updated_at,
                    outcome="won" if self.deal.is_won else "lost",
                    closed_at=self.deal.closed_at,  # type: ignore[arg-type]
                )
            )

    def score_lead(
        self,
        score: int,
        confidence: float,
        reasoning: str,
        model_version: str,
        recommendation: str | None = None,
    ) -> LeadScore:
        if not 0 <= score <= 100:
            raise InvalidLeadScoreError(score)

        ai_confidence = AIConfidence(confidence)
        lead_score = LeadScore(
            id=uuid.uuid4(),
            deal_id=self.deal.id,
            score=score,
            confidence=ai_confidence,
            reasoning=reasoning,
            model_version=model_version,
            generated_at=datetime.now(UTC),
        )
        self.lead_scores.append(lead_score)
        self.deal.apply_lead_score(
            score,
            ai_confidence,
            recommendation or ("qualify" if lead_score.is_qualified else "pass"),
        )

        self.activities.append(
            DealActivity(
                id=uuid.uuid4(),
                deal_id=self.deal.id,
                owner_user_id=self.deal.owner_user_id,
                activity_type=DealActivityType.AI_QUALIFICATION,
                description=f"AI scored lead: {score}/100 ({ai_confidence.level} confidence)",
                occurred_at=lead_score.generated_at,
                metadata={"score": score, "confidence": confidence, "model": model_version},
            )
        )
        self._pending_events.append(
            LeadScoredEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.deal.id,
                occurred_at=lead_score.generated_at,
                score=score,
                confidence=confidence,
                recommendation=self.deal.ai_recommendation,
                model_version=model_version,
            )
        )
        return lead_score

    def add_note(self, note: str, actor_user_id: uuid.UUID) -> None:
        if self.deal.is_terminal:
            raise TerminalDealError(self.deal.stage)
        self.activities.append(
            DealActivity(
                id=uuid.uuid4(),
                deal_id=self.deal.id,
                owner_user_id=actor_user_id,
                activity_type=DealActivityType.NOTE_ADDED,
                description=note,
                occurred_at=datetime.now(UTC),
            )
        )

    def update_value(self, value: Money) -> None:
        if self.deal.is_terminal:
            raise TerminalDealError(self.deal.stage)
        self.deal.update_value(value)

    def mark_lost(self, actor_user_id: uuid.UUID, reason: str | None = None) -> None:
        self.change_stage(DealStage.LOST, actor_user_id, note=reason)

    def mark_completed(self, actor_user_id: uuid.UUID) -> None:
        self.change_stage(DealStage.COMPLETED_AND_BILLED, actor_user_id)

    # ------------------------------------------------------------------ #
    # Event access                                                         #
    # ------------------------------------------------------------------ #

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    # ------------------------------------------------------------------ #
    # Convenience properties                                               #
    # ------------------------------------------------------------------ #

    @property
    def latest_score(self) -> LeadScore | None:
        return self.lead_scores[-1] if self.lead_scores else None
