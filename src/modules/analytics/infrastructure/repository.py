from dataclasses import dataclass
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import AiCostRecordModel, ClientModel, DealModel, InvoiceModel, UsageRecordModel


@dataclass
class AnalyticsRepository:
    db: AsyncSession

    async def dashboard_counts(self, owner_user_id: uuid.UUID) -> tuple[int, int, object, int]:
        clients = await self.db.scalar(select(func.count()).select_from(ClientModel).where(ClientModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None))) or 0
        active_deals = await self.db.scalar(select(func.count()).select_from(DealModel).where(DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None), DealModel.stage.notin_(["completed_and_billed", "lost"]))) or 0
        revenue = await self.db.scalar(select(func.sum(InvoiceModel.total)).where(InvoiceModel.owner_user_id == owner_user_id, InvoiceModel.status == "paid")) or 0
        pending = await self.db.scalar(select(func.count()).select_from(InvoiceModel).where(InvoiceModel.owner_user_id == owner_user_id, InvoiceModel.status.in_(["draft", "sent"]))) or 0
        return clients, active_deals, revenue, pending

    async def revenue(self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None) -> dict:
        conditions = [InvoiceModel.owner_user_id == owner_user_id]
        if from_date is not None: conditions.append(InvoiceModel.issue_date >= from_date)
        if to_date is not None: conditions.append(InvoiceModel.issue_date <= to_date)
        row = (await self.db.execute(select(func.coalesce(func.sum(InvoiceModel.total), 0), func.coalesce(func.sum(InvoiceModel.amount_paid), 0)).where(*conditions))).one()
        return {"total_invoiced": row[0], "total_collected": row[1], "total_outstanding": row[0] - row[1]}

    async def pipeline(self, owner_user_id: uuid.UUID) -> list[dict]:
        rows = (await self.db.execute(select(DealModel.stage, func.count(DealModel.id), func.coalesce(func.sum(DealModel.estimated_value), 0)).where(DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)).group_by(DealModel.stage))).all()
        return [{"stage": r[0], "deal_count": r[1], "total_value": r[2]} for r in rows]

    async def win_rate(self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None) -> dict:
        conditions = [DealModel.owner_user_id == owner_user_id, DealModel.deleted_at.is_(None)]
        if from_date is not None: conditions.append(func.date(DealModel.closed_at) >= from_date)
        if to_date is not None: conditions.append(func.date(DealModel.closed_at) <= to_date)
        won = await self.db.scalar(select(func.count()).select_from(DealModel).where(*conditions, DealModel.stage == "completed_and_billed")) or 0
        lost = await self.db.scalar(select(func.count()).select_from(DealModel).where(*conditions, DealModel.stage == "lost")) or 0
        total = won + lost
        return {"won": won, "lost": lost, "win_rate": (won / total if total else 0)}

    async def top_clients(self, owner_user_id: uuid.UUID, limit: int = 10, from_date: date | None = None, to_date: date | None = None, metric: str = "total_collected") -> list[dict]:
        amount_expr = InvoiceModel.total if metric == "total_invoiced" else InvoiceModel.amount_paid
        conditions = [ClientModel.owner_user_id == owner_user_id, InvoiceModel.owner_user_id == owner_user_id, ClientModel.deleted_at.is_(None)]
        if from_date is not None: conditions.append(InvoiceModel.issue_date >= from_date)
        if to_date is not None: conditions.append(InvoiceModel.issue_date <= to_date)
        rows = (await self.db.execute(select(ClientModel.id, ClientModel.name, func.coalesce(func.sum(amount_expr), 0).label("revenue")).join(InvoiceModel, InvoiceModel.client_id == ClientModel.id).where(*conditions).group_by(ClientModel.id, ClientModel.name).order_by(func.coalesce(func.sum(amount_expr), 0).desc()).limit(limit))).all()
        return [{"client_id": r[0], "name": r[1], "revenue": r[2]} for r in rows]

    async def ai_usage(self, owner_user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None) -> dict:
        conditions = [AiCostRecordModel.user_id == owner_user_id]
        if from_date is not None: conditions.append(func.date(AiCostRecordModel.occurred_at) >= from_date)
        if to_date is not None: conditions.append(func.date(AiCostRecordModel.occurred_at) <= to_date)
        cost = await self.db.scalar(select(func.coalesce(func.sum(AiCostRecordModel.estimated_cost_usd), 0)).where(*conditions)) or 0
        generations = await self.db.scalar(select(func.coalesce(func.sum(UsageRecordModel.ai_generations_used), 0)).where(UsageRecordModel.user_id == owner_user_id)) or 0
        return {"generations_used": generations, "estimated_cost_usd": cost}
