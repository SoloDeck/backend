"""Clients application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.clients.infrastructure.repository import ClientsRepository
from src.modules.clients.schemas.request import ClientRequest, CommLogRequest
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError


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
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        from sqlalchemy import func, select

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

        from src.infrastructure.database.models import DealModel

        total_result = await self.db.execute(
            select(func.count()).select_from(ClientModel).where(*conditions)
        )
        total = total_result.scalar_one()

        deal_count_subq = (
            select(func.count(DealModel.id))
            .where(
                DealModel.client_id == ClientModel.id,
                DealModel.deleted_at.is_(None),
            )
            .correlate(ClientModel)
            .scalar_subquery()
        )

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            select(ClientModel, deal_count_subq.label("deal_count"))
            .where(*conditions)
            .offset(offset)
            .limit(page_size)
        )

        clients = []
        for client, count in rows.all():
            client.deal_count = count
            clients.append(client)
        return clients, total

    async def get_one(self, user_id: uuid.UUID, client_id: uuid.UUID):  # type: ignore[return]
        return await self._get_client(user_id, client_id)

    async def update(self, user_id: uuid.UUID, client_id: uuid.UUID, payload: ClientRequest):  # type: ignore[return]
        client = await self._get_client(user_id, client_id)
        for field in (
            "name",
            "email",
            "phone",
            "type",
            "website",
            "linkedin_url",
            "address_city",
            "address_country",
            "status",
            "notes",
            "description",
        ):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(client, field, value)
        return await self.repo.save(client)

    async def delete(self, user_id: uuid.UUID, client_id: uuid.UUID) -> None:
        client = await self._get_client(user_id, client_id)
        if await self.repo.has_transactions(client_id):
            raise BusinessRuleError(
                "Cannot delete a client that has existing deals, invoices, or contracts."
            )
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
