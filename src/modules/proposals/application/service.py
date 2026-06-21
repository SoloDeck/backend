"""Proposals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.proposals.schemas.request import ProposalRequest
from src.shared.events.bus import event_bus
from src.shared.exceptions.domain import BusinessRuleError, InvalidStateTransitionError, NotFoundError

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent"}),
    "sent": frozenset({"accepted", "rejected", "expired"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "expired": frozenset(),
    "superseded": frozenset(),
}


@dataclass
class ProposalsService:
    db: AsyncSession

    async def _get_proposal(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import ProposalModel

        proposal = await self.db.scalar(
            select(ProposalModel).where(
                ProposalModel.id == proposal_id,
                ProposalModel.owner_user_id == user_id,
            )
        )
        if proposal is None:
            raise NotFoundError(f"Proposal {proposal_id} not found")
        return proposal

    async def create(self, user_id: uuid.UUID, payload: ProposalRequest, *, ai_generated: bool = False):  # type: ignore[return]
        from src.infrastructure.database.models import ProposalModel

        count_result = await self.db.scalar(
            select(func.count()).select_from(ProposalModel).where(
                ProposalModel.deal_id == payload.deal_id
            )
        )
        version_number = (count_result or 0) + 1

        proposal = ProposalModel(
            deal_id=payload.deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status=payload.status,
            content=payload.content,
            ai_generated=ai_generated,
        )
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        from src.infrastructure.database.models import ProposalModel

        conditions = [ProposalModel.owner_user_id == user_id]
        if status is not None:
            conditions.append(ProposalModel.status == status)
        if deal_id is not None:
            conditions.append(ProposalModel.deal_id == deal_id)

        total = await self.db.scalar(
            select(func.count()).select_from(ProposalModel).where(*conditions)
        ) or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ProposalModel)
            .where(*conditions)
            .order_by(ProposalModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_one(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_proposal(user_id, proposal_id)

    async def update(self, user_id: uuid.UUID, proposal_id: uuid.UUID, payload: ProposalRequest):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"Proposal content can only be edited in draft status "
                f"(current status: '{proposal.status}')"
            )
        if payload.content:
            proposal.content = payload.content
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def delete(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
        proposal = await self._get_proposal(user_id, proposal_id)
        await self.db.delete(proposal)
        await self.db.flush()

    async def generate_content(self, user_id: uuid.UUID, proposal_id: uuid.UUID, ai_facade):  # type: ignore[return]
        from src.infrastructure.database.models import ClientModel, DealModel, PlanModel, SubscriptionModel, UserModel

        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"AI generation is only available for draft proposals (current status: '{proposal.status}')"
            )

        sub = await self.db.scalar(select(SubscriptionModel).where(SubscriptionModel.user_id == user_id))
        plan = await self.db.scalar(select(PlanModel).where(PlanModel.id == sub.plan_id)) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        deal = await self.db.scalar(select(DealModel).where(DealModel.id == proposal.deal_id))
        client = await self.db.scalar(select(ClientModel).where(ClientModel.id == deal.client_id)) if deal else None
        user = await self.db.scalar(select(UserModel).where(UserModel.id == user_id))

        content = await ai_facade.generate_proposal(
            deal_data={"title": deal.title if deal else "", "stage": deal.stage if deal else "", "notes": deal.notes if deal else ""},
            client_data={"name": client.name if client else "", "email": client.email if client else ""},
            user_profile={"name": user.full_name if user else "", "email": user.email if user else ""},
            template=None,
            user_can_use_ai=user_can_use_ai,
        )
        proposal.content = content
        proposal.ai_generated = True
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def transition_status(
        self, user_id: uuid.UUID, proposal_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        from src.infrastructure.database.models import ProposalModel

        proposal = await self._get_proposal(user_id, proposal_id)
        current = proposal.status
        allowed = _VALID_TRANSITIONS.get(current, frozenset())
        if target_status not in allowed:
            raise InvalidStateTransitionError("proposal", current, target_status)

        now = datetime.now(UTC)

        if target_status == "sent":
            # Supersede any existing sent proposal on the same deal
            existing = await self.db.scalar(
                select(ProposalModel).where(
                    ProposalModel.deal_id == proposal.deal_id,
                    ProposalModel.status == "sent",
                    ProposalModel.id != proposal_id,
                )
            )
            if existing is not None:
                existing.status = "superseded"
            proposal.sent_at = now

        if target_status in ("accepted", "rejected", "expired"):
            proposal.responded_at = now

        proposal.status = target_status
        await self.db.flush()
        await self.db.refresh(proposal)

        if target_status == "accepted":
            await event_bus.publish(
                "proposals.proposal_accepted",
                {"proposal_id": str(proposal_id), "deal_id": str(proposal.deal_id),
                 "owner_user_id": str(user_id)},
            )
        elif target_status == "sent":
            await event_bus.publish(
                "proposals.proposal_sent",
                {"proposal_id": str(proposal_id), "deal_id": str(proposal.deal_id),
                 "owner_user_id": str(user_id)},
            )

        return proposal
