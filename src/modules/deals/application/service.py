"""Deals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.deals.domain.aggregates.deal_aggregate import DealAggregate
from src.modules.deals.domain.entities.deal import Deal
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence
from src.modules.deals.domain.value_objects.deal_stage import DealStage, STAGE_TRANSITIONS, TERMINAL_STAGES
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.shared.exceptions.domain import BusinessRuleError, InvalidStateTransitionError, NotFoundError
from src.shared.rate_limit import FixedWindowRateLimiter

from src.ai.facade import AIFacade

# Basic per-link guard for the public, unauthenticated intake form. Process-local;
# a generous window so legitimate submissions are unaffected while a flood of
# automated posts to a single share link is throttled (returns HTTP 429).
_public_intake_limiter = FixedWindowRateLimiter(max_requests=20, window_seconds=60)

@dataclass
class DealsService:
    db: AsyncSession
    ai_facade: AIFacade | None = None
    repo: DealsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = DealsRepository(self.db)

    async def _get_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        deal = await self.repo.get_by_id(deal_id, user_id)
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal

    async def _get_intake(
            self,
            user_id: uuid.UUID,
            intake_id: uuid.UUID,
    ):
        intake = await self.repo.get_intake_by_id(intake_id, user_id)

        if intake is None:
            raise NotFoundError(f"Deal intake {intake_id} not found")

        return intake

    async def create(self, user_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        client = await self.repo.get_client_by_id(payload.client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {payload.client_id} not found")
        return await self.repo.create(
            owner_user_id=user_id,
            client_id=payload.client_id,
            title=payload.title,
            stage=payload.stage,
            source=payload.source,
            estimated_value=payload.estimated_value,
            actual_value=payload.actual_value,
            currency=payload.currency,
            notes=payload.notes,
            project_type=payload.project_type,
            service_category=payload.service_category,
            pricing_tier=payload.pricing_tier,
        )

    async def create_public_intake(self, share_token: str, payload: PublicIntakeRequest):
        """Capture a lead submitted through the owner's public intake link.

        No authentication: the owner is resolved solely from the hard-to-guess
        `share_token`. Creates a minimal prospect Client, a `new_lead` Deal (so it
        surfaces in the owner's pipeline / GET /deals) and a DealIntake holding the
        raw inquiry for later AI qualification (Package 3 — no scoring here).
        """
        # Throttle by the raw token first so both valid and invalid links are
        # rate-limited (basic abuse guard) before any DB work.
        _public_intake_limiter.check(share_token)

        owner = await self.repo.get_owner_by_intake_token(share_token)
        if owner is None:
            raise NotFoundError("Intake form not found or link is invalid")

        client = await self.repo.create_client(
            owner_user_id=owner.id,
            type="individual",
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            status="prospect",
        )
        await self.repo.create(
            owner_user_id=owner.id,
            client_id=client.id,
            title=payload.project_name or f"Intake — {payload.name}",
            stage="new_lead",
            source="inbound",
            currency=owner.currency,
        )
        return await self.repo.create_intake(
            owner_user_id=owner.id,
            client_id=client.id,
            inquiry_text=payload.inquiry_text or "",
            estimated_budget=payload.estimated_budget,
            desired_timeline=payload.desired_timeline,
            source="inbound",
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        stage: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(user_id, title=title, stage=stage, page=page, page_size=page_size)

    async def get_one(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_deal(user_id, deal_id)

    async def update(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        for field in ("title", "source", "estimated_value", "actual_value", "currency", "notes",
                      "project_type", "service_category", "pricing_tier"):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(deal, field, value)
        return await self.repo.save(deal)

    async def delete(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> None:
        deal = await self._get_deal(user_id, deal_id)
        deal.deleted_at = datetime.now(UTC)
        await self.repo.save(deal)

    async def transition_stage(
        self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealStageRequest
    ):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        try:
            current = DealStage(deal.stage)
            target = DealStage(payload.stage)
        except ValueError as exc:
            raise BusinessRuleError("Invalid deal stage") from exc
        if target not in STAGE_TRANSITIONS.get(current, frozenset()):
            raise InvalidStateTransitionError("deal", deal.stage, payload.stage)
        if target == DealStage.ACTIVE and not await self.repo.has_accepted_proposal(deal_id, user_id):
            raise BusinessRuleError("Transitioning to active requires an accepted proposal")
        if target == DealStage.COMPLETED_AND_BILLED and not await self.repo.has_invoice(deal_id, user_id):
            raise BusinessRuleError("Transitioning to completed_and_billed requires a linked invoice")
        deal.stage = payload.stage
        if target in TERMINAL_STAGES and hasattr(deal, "closed_at"):
            deal.closed_at = datetime.now(UTC)
            await self.repo.cancel_pending_reminders(deal_id, user_id)
        return await self.repo.save(deal)

    async def qualify_deal_intake(
            self,
            user_id: uuid.UUID,
            intake_id: uuid.UUID,
    ):
        intake = await self._get_intake(user_id, intake_id)

        if not intake.inquiry_text:
            raise ValueError("Deal intake has no inquiry text")

        if not self.ai_facade:
            raise RuntimeError("AIFacade not initialized")

        result = await self.ai_facade.qualify_lead(
            inquiry_text=intake.inquiry_text,
            user_can_use_ai=True,  # TODO: get from subscriptions
        )

        _score_map = {"HOT": 80, "WARM": 50, "COLD": 20}
        _confidence_map = {"HOT": AIConfidence.high(), "WARM": AIConfidence.medium(), "COLD": AIConfidence.low()}
        raw = str(result.get("suggested_lead_score", "")).upper()
        score = _score_map.get(raw, 50)
        confidence = _confidence_map.get(raw, AIConfidence.medium())
        reasoning = str(result.get("reasoning", ""))
        model_version = "gemma-4-31b-it"

        deal_model = await self.repo.get_deal_by_client_id(intake.client_id, user_id)
        if deal_model is not None:
            # Build a minimal domain Deal so the aggregate can run its logic
            deal_domain = Deal(
                id=deal_model.id,
                owner_user_id=deal_model.owner_user_id,
                client_id=deal_model.client_id,
                title=deal_model.title,
                stage=DealStage(deal_model.stage),
                value=None,
                source=deal_model.source,
                expected_close_date=None,
                ai_score=deal_model.ai_qualification_score,
                ai_confidence=None,
                ai_recommendation=deal_model.ai_qualification_recommendation,
                closed_at=deal_model.closed_at,
                created_at=deal_model.created_at,
                updated_at=deal_model.updated_at,
                deleted_at=deal_model.deleted_at,
            )
            aggregate = DealAggregate(deal=deal_domain)
            lead_score = aggregate.score_lead(
                score=score,
                confidence=confidence.value,
                reasoning=reasoning,
                model_version=model_version,
            )

            await self.repo.create_lead_score(
                id=lead_score.id,
                deal_id=lead_score.deal_id,
                score=lead_score.score,
                confidence=lead_score.confidence.value,
                reasoning=lead_score.reasoning,
                model_version=lead_score.model_version,
                generated_at=lead_score.generated_at,
                project_type=result.get("project_type"),
                budget_signal=result.get("budget_signal"),
                timeline_signal=result.get("timeline_signal"),
                urgency_signal=result.get("urgency_signal"),
                red_flags=result.get("red_flags"),
            )

            deal_model.ai_qualification_score = lead_score.score
            deal_model.ai_qualification_confidence = lead_score.confidence.value
            deal_model.ai_qualification_recommendation = aggregate.deal.ai_recommendation
            await self.repo.save(deal_model)

        return {**result, "ai_qualification_score": score, "ai_qualification_recommendation": aggregate.deal.ai_recommendation if deal_model else None}

