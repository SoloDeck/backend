"""Analytics API api."""

from typing import Annotated

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.analytics.application.service import AnalyticsService
from src.modules.analytics.schemas.response import AiUsageResponse, DashboardResponse, PipelineStageResponse, RevenueResponse, TopClientResponse, WinRateResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/dashboard", response_model=ApiResponse[DashboardResponse])
async def get_dashboard(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DashboardResponse]:
    result = await AnalyticsService(db=db).get_dashboard(user_id)
    return ApiResponse.ok(result)


@router.get("/revenue", response_model=ApiResponse[RevenueResponse])
async def get_revenue(
    user_id: CurrentUserId,
    db: DBSession,
    period_type: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> ApiResponse[RevenueResponse]:
    return ApiResponse.ok(await AnalyticsService(db=db).get_revenue(user_id, period_type, from_date, to_date))


@router.get("/pipeline", response_model=ApiResponse[list[PipelineStageResponse]])
async def get_pipeline(
    user_id: CurrentUserId,
    db: DBSession,
    snapshot_date: date | None = Query(default=None),
) -> ApiResponse[list[PipelineStageResponse]]:
    return ApiResponse.ok(await AnalyticsService(db=db).get_pipeline(user_id, snapshot_date))


@router.get("/win-rate", response_model=ApiResponse[WinRateResponse])
async def get_win_rate(
    user_id: CurrentUserId,
    db: DBSession,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> ApiResponse[WinRateResponse]:
    return ApiResponse.ok(await AnalyticsService(db=db).get_win_rate(user_id, from_date, to_date))


@router.get("/clients/top", response_model=ApiResponse[list[TopClientResponse]])
async def get_top_clients(
    user_id: CurrentUserId,
    db: DBSession,
    limit: int = Query(default=10, ge=1, le=50),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    metric: str = Query(default="total_collected"),
) -> ApiResponse[list[TopClientResponse]]:
    return ApiResponse.ok(await AnalyticsService(db=db).get_top_clients(user_id, limit, from_date, to_date, metric))


@router.get("/ai-usage", response_model=ApiResponse[AiUsageResponse])
async def get_ai_usage(
    user_id: CurrentUserId,
    db: DBSession,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> ApiResponse[AiUsageResponse]:
    return ApiResponse.ok(await AnalyticsService(db=db).get_ai_usage(user_id, from_date, to_date))
