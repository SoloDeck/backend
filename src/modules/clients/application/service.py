"""Clients application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import NotFoundError
from src.modules.clients.infrastructure.repository import ClientsRepository
from src.modules.clients.schemas.request import ClientRequest, CommLogRequest


@dataclass
class ClientsService:
    db: AsyncSession
    repo: ClientsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ClientsRepository(self.db)

    async def _get_client(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        client = await self.repo.get_by_id(client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {client_id} not found")
        return client

    async def create(self, user_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        return await self.repo.create(
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

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        name: str | None = None,
        email: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, status=status, name=name, email=email)

    async def get_one(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        return await self._get_client(user_id, client_id)

    async def update(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        client = await self._get_client(user_id, client_id)
        for field in ("name", "email", "phone", "type", "website", "linkedin_url",
                      "address_city", "address_country", "status", "notes", "description"):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(client, field, value)
        return await self.repo.save(client)

    async def delete(self, user_id: uuid.UUID, client_id: uuid.UUID) -> None:
        client = await self._get_client(user_id, client_id)
        client.deleted_at = datetime.now(UTC)
        await self.repo.save(client)

    async def add_comm_log(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: CommLogRequest):  # type: ignore[return]
        await self._get_client(user_id, client_id)
        return await self.repo.add_comm_log(
            client_id=client_id,
            owner_user_id=user_id,
            channel=payload.channel,
            summary=payload.summary,
            communicated_at=payload.communicated_at,
        )

    async def list_comm_logs(self, user_id: uuid.UUID, client_id: uuid.UUID) -> list:
        await self._get_client(user_id, client_id)
        return await self.repo.list_comm_logs(user_id, client_id)

