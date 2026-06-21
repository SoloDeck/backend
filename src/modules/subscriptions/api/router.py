"""Subscriptions API api."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.schemas.response import PlanResponse, SubscriptionResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/plans", response_model=ApiResponse[list[PlanResponse]])
async def list_plans(
    db: DBSession,
) -> ApiResponse[list[PlanResponse]]:
    plans = await SubscriptionsService(db=db).list_plans()
    return ApiResponse.ok([PlanResponse.model_validate(p) for p in plans])


@router.get("/me", response_model=ApiResponse[SubscriptionResponse])
async def get_my_subscription(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[SubscriptionResponse]:
    sub = await SubscriptionsService(db=db).get_my_subscription(user_id)
    return ApiResponse.ok(sub)
