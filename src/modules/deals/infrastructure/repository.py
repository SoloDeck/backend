from dataclasses import dataclass
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ClientModel, DealIntakeModel, DealModel, InvoiceModel, ProposalModel, ReminderModel


@dataclass
class DealsRepository:
    db: AsyncSession

    async def get_by_id(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(select(DealModel).where(DealModel.id == deal_id, DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)))

    async def get_intake_by_id(self, intake_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(select(DealIntakeModel).where(DealIntakeModel.id == intake_id, DealIntakeModel.owner_user_id == owner_user_id, DealIntakeModel.deleted_at.is_(None)))

    async def get_client_by_id(self, client_id: uuid.UUID, owner_user_id: uuid.UUID):
        return await self.db.scalar(select(ClientModel).where(ClientModel.id == client_id, ClientModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None)))

    async def has_accepted_proposal(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        count = await self.db.scalar(select(func.count()).select_from(ProposalModel).where(ProposalModel.deal_id == deal_id, ProposalModel.owner_user_id == owner_user_id, ProposalModel.status == "accepted"))
        return bool(count)

    async def has_invoice(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> bool:
        count = await self.db.scalar(select(func.count()).select_from(InvoiceModel).where(InvoiceModel.deal_id == deal_id, InvoiceModel.owner_user_id == owner_user_id))
        return bool(count)

    async def cancel_pending_reminders(self, deal_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        await self.db.execute(update(ReminderModel).where(ReminderModel.owner_user_id == owner_user_id, ReminderModel.target_type == "deal", ReminderModel.target_id == deal_id, ReminderModel.status == "pending").values(status="cancelled"))

    async def create(self, **values):
        deal = DealModel(**values)
        self.db.add(deal)
        await self.db.flush(); await self.db.refresh(deal)
        return deal

    async def list_all(self, owner_user_id: uuid.UUID, title: str | None = None, stage: str | None = None) -> list:
        conditions = [DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)]
        if title is not None: conditions.append(DealModel.title.ilike(f"%{title}%"))
        if stage is not None: conditions.append(DealModel.stage == stage)
        result = await self.db.execute(select(DealModel).where(*conditions))
        return list(result.scalars().all())

    async def save(self, obj):
        await self.db.flush(); await self.db.refresh(obj)
        return obj
