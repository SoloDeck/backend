import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientCommunicationLogModel,
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceModel,
)


@dataclass
class ClientsRepository:
    db: AsyncSession

    async def get_by_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.owner_user_id == owner_user_id,
                ClientModel.deleted_at.is_(None),
            )
        )

    async def create(self, **values):
        client = ClientModel(**values)
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def list_all(
        self,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        name: str | None = None,
        email: str | None = None,
    ) -> list:
        conditions = [ClientModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None)]
        if status is not None:
            conditions.append(ClientModel.status == status)
        if name is not None:
            conditions.append(ClientModel.name.ilike(f"%{name}%"))
        if email is not None:
            conditions.append(ClientModel.email.ilike(f"%{email}%"))
        result = await self.db.execute(select(ClientModel).where(*conditions))
        return list(result.scalars().all())

    async def add_comm_log(self, **values):
        log = ClientCommunicationLogModel(**values)
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def list_comm_logs(self, owner_user_id: uuid.UUID, client_id: uuid.UUID) -> list:
        result = await self.db.execute(
            select(ClientCommunicationLogModel).where(
                ClientCommunicationLogModel.client_id == client_id,
                ClientCommunicationLogModel.owner_user_id == owner_user_id,
            )
        )
        return list(result.scalars().all())

    async def has_transactions(self, client_id: uuid.UUID) -> bool:
        """Return True if the client has any deals, invoices, or contracts."""
        for Model in (DealModel, InvoiceModel, ContractModel):
            found = await self.db.scalar(
                select(exists().where(Model.client_id == client_id))
            )
            if found:
                return True
        return False

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
