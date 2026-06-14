"""Analytics application service."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.analytics.infrastructure.repository import AnalyticsRepository
from src.modules.analytics.schemas.response import AiUsageResponse, DashboardResponse, PipelineStageResponse, RevenueResponse, TopClientResponse, WinRateResponse


@dataclass
class AnalyticsService:
    db: AsyncSession
    repo: AnalyticsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AnalyticsRepository(self.db)

    async def get_dashboard(self, user_id: uuid.UUID) -> DashboardResponse:
        total_clients, active_deals, total_revenue_raw, pending_invoices = await self.repo.dashboard_counts(user_id)
        total_revenue = Decimal(str(total_revenue_raw))

        return DashboardResponse(
            total_clients=total_clients,
            active_deals=active_deals,
            total_revenue=total_revenue,
            pending_invoices=pending_invoices,
        )

    async def get_revenue(self, user_id: uuid.UUID, period_type: str | None = None, from_date: date | None = None, to_date: date | None = None) -> RevenueResponse:
        return RevenueResponse(**await self.repo.revenue(user_id, from_date, to_date))

    async def get_pipeline(self, user_id: uuid.UUID, snapshot_date: date | None = None) -> list[PipelineStageResponse]:
        return [PipelineStageResponse(**x) for x in await self.repo.pipeline(user_id)]

    async def get_win_rate(self, user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None) -> WinRateResponse:
        return WinRateResponse(**await self.repo.win_rate(user_id, from_date, to_date))

    async def get_top_clients(self, user_id: uuid.UUID, limit: int = 10, from_date: date | None = None, to_date: date | None = None, metric: str = "total_collected") -> list[TopClientResponse]:
        return [TopClientResponse(**x) for x in await self.repo.top_clients(user_id, limit, from_date, to_date, metric)]

    async def get_ai_usage(self, user_id: uuid.UUID, from_date: date | None = None, to_date: date | None = None) -> AiUsageResponse:
        return AiUsageResponse(**await self.repo.ai_usage(user_id, from_date, to_date))
