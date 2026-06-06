"""Contracts application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import NotFoundError
from src.modules.contracts.schemas.request import ContractRequest


@dataclass
class ContractsService:
    db: AsyncSession

    async def _get_contract(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import ContractModel

        contract = await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == user_id,
            )
        )
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def create(self, user_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ContractModel, ClientModel

        count_result = await self.db.scalar(
            select(func.count()).select_from(ContractModel).where(
                ContractModel.deal_id == payload.deal_id
            )
        )
        version_number = (count_result or 0) + 1

        client = await self.db.scalar(
            select(ClientModel).where(ClientModel.id == payload.client_id)
        )
        client_snapshot: dict = {}
        if client is not None:
            client_snapshot = {
                "id": str(client.id),
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
            }

        contract = ContractModel(
            deal_id=payload.deal_id,
            proposal_id=payload.proposal_id,
            client_id=payload.client_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=payload.content,
            client_snapshot=client_snapshot,
        )
        self.db.add(contract)
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ContractModel

        result = await self.db.execute(
            select(ContractModel).where(ContractModel.owner_user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self._get_contract(user_id, contract_id)

    async def update(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if payload.content:
            contract.content = payload.content
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def delete(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> None:
        contract = await self._get_contract(user_id, contract_id)
        await self.db.delete(contract)
        await self.db.flush()
