"""Analytics application service."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.analytics.schemas.response import DashboardResponse


@dataclass
class AnalyticsService:
    db: AsyncSession

    async def get_dashboard(self, user_id: uuid.UUID) -> DashboardResponse:
        from src.infrastructure.database.models import ClientModel, DealModel, InvoiceModel

        total_clients = await self.db.scalar(
            select(func.count()).select_from(ClientModel).where(
                ClientModel.owner_user_id == user_id,
                ClientModel.deleted_at.is_(None),
            )
        ) or 0

        active_deals = await self.db.scalar(
            select(func.count()).select_from(DealModel).where(
                DealModel.owner_user_id == user_id,
                DealModel.deleted_at.is_(None),
                DealModel.stage.notin_(["completed_and_billed", "lost"]),
            )
        ) or 0

        total_revenue_raw = await self.db.scalar(
            select(func.sum(InvoiceModel.total)).where(
                InvoiceModel.owner_user_id == user_id,
                InvoiceModel.status == "paid",
            )
        )
        total_revenue = Decimal(str(total_revenue_raw)) if total_revenue_raw is not None else Decimal("0")

        pending_invoices = await self.db.scalar(
            select(func.count()).select_from(InvoiceModel).where(
                InvoiceModel.owner_user_id == user_id,
                InvoiceModel.status.in_(["draft", "sent"]),
            )
        ) or 0

        return DashboardResponse(
            total_clients=total_clients,
            active_deals=active_deals,
            total_revenue=total_revenue,
            pending_invoices=pending_invoices,
        )
