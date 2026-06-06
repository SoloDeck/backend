"""Analytics API router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.analytics.application.service import AnalyticsService
from src.modules.analytics.schemas.response import DashboardResponse
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
