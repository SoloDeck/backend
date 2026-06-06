"""Proposals application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import NotFoundError
from src.modules.proposals.schemas.request import ProposalRequest


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

    async def create(self, user_id: uuid.UUID, payload: ProposalRequest):  # type: ignore[return]
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
            ai_generated=False,
        )
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ProposalModel

        result = await self.db.execute(
            select(ProposalModel).where(ProposalModel.owner_user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_proposal(user_id, proposal_id)

    async def update(self, user_id: uuid.UUID, proposal_id: uuid.UUID, payload: ProposalRequest):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if payload.content:
            proposal.content = payload.content
        if payload.status:
            proposal.status = payload.status
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def delete(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
        proposal = await self._get_proposal(user_id, proposal_id)
        await self.db.delete(proposal)
        await self.db.flush()
