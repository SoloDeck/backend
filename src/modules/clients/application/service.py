"""Clients application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import NotFoundError
from src.modules.clients.schemas.request import ClientRequest, CommLogRequest


@dataclass
class ClientsService:
    db: AsyncSession

    async def _get_client(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import ClientModel

        client = await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id,
                ClientModel.owner_user_id == user_id,
                ClientModel.deleted_at.is_(None),
            )
        )
        if client is None:
            raise NotFoundError(f"Client {client_id} not found")
        return client

    async def create(self, user_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ClientModel

        client = ClientModel(
            owner_user_id=user_id,
            type=payload.type,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            website=payload.website,
            linkedin_url=payload.linkedin_url,
            address_city=payload.address_city,
            address_country=payload.address_country,
            status=payload.status,
            notes=payload.notes,
            description=payload.description,
        )
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        name: str | None = None,
        email: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        from sqlalchemy import func
        from src.infrastructure.database.models import ClientModel

        conditions = [
            ClientModel.owner_user_id == user_id,
            ClientModel.deleted_at.is_(None),
        ]
        if status is not None:
            conditions.append(ClientModel.status == status)
        if name is not None:
            conditions.append(ClientModel.name.ilike(f"%{name}%"))
        if email is not None:
            conditions.append(ClientModel.email.ilike(f"%{email}%"))

        total_result = await self.db.execute(
            select(func.count()).select_from(ClientModel).where(*conditions)
        )
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ClientModel).where(*conditions).offset(offset).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_one(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        return await self._get_client(user_id, client_id)

    async def update(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        client = await self._get_client(user_id, client_id)
        for field in ("name", "email", "phone", "type", "website", "linkedin_url",
                      "address_city", "address_country", "status", "notes", "description"):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(client, field, value)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def delete(self, user_id: uuid.UUID, client_id: uuid.UUID) -> None:
        client = await self._get_client(user_id, client_id)
        client.deleted_at = datetime.now(UTC)
        await self.db.flush()

    async def add_comm_log(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: CommLogRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ClientCommunicationLogModel

        await self._get_client(user_id, client_id)
        log = ClientCommunicationLogModel(
            client_id=client_id,
            owner_user_id=user_id,
            channel=payload.channel,
            summary=payload.summary,
            communicated_at=payload.communicated_at,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def list_comm_logs(self, user_id: uuid.UUID, client_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ClientCommunicationLogModel

        await self._get_client(user_id, client_id)
        result = await self.db.execute(
            select(ClientCommunicationLogModel).where(
                ClientCommunicationLogModel.client_id == client_id,
                ClientCommunicationLogModel.owner_user_id == user_id,
            )
        )
        return list(result.scalars().all())


