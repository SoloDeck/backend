"""Clients application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.clients.schemas.request import ClientRequest, CommLogRequest, TagRequest
from src.shared.exceptions.domain import NotFoundError


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
        )
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def list_all(self, user_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ClientModel

        result = await self.db.execute(
            select(ClientModel).where(
                ClientModel.owner_user_id == user_id,
                ClientModel.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_one(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        return await self._get_client(user_id, client_id)

    async def update(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        client = await self._get_client(user_id, client_id)
        for field in ("name", "email", "phone", "type", "website", "linkedin_url",
                      "address_city", "address_country", "status", "notes"):
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

    async def add_tag(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: TagRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ClientTagModel

        await self._get_client(user_id, client_id)
        tag = ClientTagModel(client_id=client_id, tag=payload.tag)
        self.db.add(tag)
        await self.db.flush()
        await self.db.refresh(tag)
        return tag

    async def list_tags(self, user_id: uuid.UUID, client_id: uuid.UUID) -> list:
        from src.infrastructure.database.models import ClientTagModel

        await self._get_client(user_id, client_id)
        result = await self.db.execute(
            select(ClientTagModel).where(ClientTagModel.client_id == client_id)
        )
        return list(result.scalars().all())

    async def remove_tag(self, user_id: uuid.UUID, client_id: uuid.UUID, tag: str) -> None:
        from src.infrastructure.database.models import ClientTagModel

        await self._get_client(user_id, client_id)
        tag_obj = await self.db.scalar(
            select(ClientTagModel).where(
                ClientTagModel.client_id == client_id,
                ClientTagModel.tag == tag,
            )
        )
        if tag_obj is None:
            raise NotFoundError(f"Tag '{tag}' not found")
        await self.db.delete(tag_obj)
        await self.db.flush()
