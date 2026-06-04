"""Deals application service."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import InvalidStateTransitionError, NotFoundError
from src.modules.deals.schemas.request import DealRequest, DealStageRequest

VALID_TRANSITIONS: dict[str, list[str]] = {
    "new_lead": ["qualified", "lost"],
    "qualified": ["proposal_sent", "lost"],
    "proposal_sent": ["in_negotiation", "lost"],
    "in_negotiation": ["active", "lost"],
    "active": ["completed_and_billed", "lost"],
    "completed_and_billed": [],
    "lost": [],
}


@dataclass
class DealsService:
    db: AsyncSession

    async def _get_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import DealModel

        deal = await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id,
                DealModel.owner_user_id == user_id,
                DealModel.deleted_at.is_(None),
            )
        )
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal

    async def create(self, user_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        from src.infrastructure.database.models import DealModel

        deal = DealModel(
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
        self.db.add(deal)
        await self.db.flush()
        await self.db.refresh(deal)
        return deal

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import DealModel

        result = await self.db.execute(
            select(DealModel).where(
                DealModel.owner_user_id == user_id,
                DealModel.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_deal(user_id, deal_id)

    async def update(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        for field in ("title", "source", "estimated_value", "actual_value", "currency", "notes"):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(deal, field, value)
        await self.db.flush()
        await self.db.refresh(deal)
        return deal

    async def delete(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> None:
        deal = await self._get_deal(user_id, deal_id)
        deal.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def transition_stage(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealStageRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        allowed = VALID_TRANSITIONS.get(deal.stage, [])
        if payload.stage not in allowed:
            raise InvalidStateTransitionError("deal", deal.stage, payload.stage)
        deal.stage = payload.stage
        if payload.stage in ("completed_and_billed", "lost") and hasattr(deal, "closed_at"):
            deal.closed_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(deal)
        return deal
