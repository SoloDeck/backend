import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealModel,
    PlanModel,
    ProposalModel,
    SubscriptionModel,
    UserModel,
)


@dataclass
class ContractsRepository:
    db: AsyncSession

    async def get_by_id(self, contract_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == owner_user_id,
            )
        )

    async def get_proposal(self, proposal_id: uuid.UUID):
        return await self.db.scalar(
            select(ProposalModel).where(ProposalModel.id == proposal_id)
        )

    async def get_client(self, client_id: uuid.UUID):
        return await self.db.scalar(select(ClientModel).where(ClientModel.id == client_id))

    async def count_by_deal(self, deal_id: uuid.UUID) -> int:
        return await self.db.scalar(
            select(func.count()).select_from(ContractModel).where(ContractModel.deal_id == deal_id)
        ) or 0

    async def create(self, **values):
        contract = ContractModel(**values)
        self.db.add(contract)
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        conditions = [ContractModel.owner_user_id == owner_user_id]
        if status is not None:
            conditions.append(ContractModel.status == status)
        if deal_id is not None:
            conditions.append(ContractModel.deal_id == deal_id)
        total = await self.db.scalar(
            select(func.count()).select_from(ContractModel).where(*conditions)
        ) or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ContractModel)
            .where(*conditions)
            .order_by(ContractModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_deal(self, deal_id: uuid.UUID):
        return await self.db.scalar(select(DealModel).where(DealModel.id == deal_id))

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(select(UserModel).where(UserModel.id == user_id))

    async def get_subscription(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj) -> None:
        await self.db.delete(obj)
        await self.db.flush()
