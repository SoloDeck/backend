"""Deals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.deals.domain.value_objects.deal_stage import DealStage, STAGE_TRANSITIONS, TERMINAL_STAGES
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.deals.schemas.request import DealRequest, DealStageRequest
from src.shared.exceptions.domain import BusinessRuleError, InvalidStateTransitionError, NotFoundError

from src.ai.facade import AIFacade

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
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        stage: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, title=title, stage=stage)

    async def get_one(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_deal(user_id, deal_id)

    async def update(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        for field in ("title", "source", "estimated_value", "actual_value", "currency", "notes"):
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
        intake = await self._get_intake(
            user_id,
            intake_id,
        )

        if not intake.inquiry_text:
            raise ValueError(
                "Deal intake has no inquiry text"
            )

        if not self.ai_facade:
            raise RuntimeError("AIFacade not initialized")

        return await self.ai_facade.qualify_lead(
            inquiry_text=intake.inquiry_text,
            user_can_use_ai=True,  # TODO: get from subscriptions
        )

