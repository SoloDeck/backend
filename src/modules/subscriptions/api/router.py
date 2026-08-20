"""Subscriptions API api."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import PaymentProvider
from src.modules.subscriptions.schemas.request import (
    ChangePlanRequest,
    CreateSubscriptionCheckoutRequest,
)
from src.modules.subscriptions.schemas.response import (
    PaymentIntentResponse,
    PlanResponse,
    SubscriptionResponse,
    UsageRecordResponse,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.payments import MomoClientDep, ZaloPayClientDep
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


@router.post("/checkout", response_model=ApiResponse[PaymentIntentResponse], status_code=201)
async def create_checkout(
    payload: CreateSubscriptionCheckoutRequest,
    user_id: CurrentUserId,
    db: DBSession,
    momo_client: MomoClientDep,
    zalopay_client: ZaloPayClientDep,
) -> ApiResponse[PaymentIntentResponse]:
    payment = await SubscriptionsService(
        db=db, momo_client=momo_client, zalopay_client=zalopay_client
    ).initiate_checkout(
        user_id, payload.plan_id, PaymentProvider(payload.provider), payload.return_url
    )
    return ApiResponse.created(PaymentIntentResponse.from_model(payment))


@router.post("/me/cancel", response_model=ApiResponse[SubscriptionResponse])
async def cancel_subscription(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[SubscriptionResponse]:
    sub = await SubscriptionsService(db=db).cancel_subscription(user_id)
    return ApiResponse.ok(sub)


@router.post("/me/upgrade", response_model=ApiResponse[SubscriptionResponse])
async def upgrade_subscription(
    payload: ChangePlanRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[SubscriptionResponse]:
    sub = await SubscriptionsService(db=db).upgrade_subscription(user_id, payload.plan_id)
    return ApiResponse.ok(sub)


@router.post("/me/downgrade", response_model=ApiResponse[SubscriptionResponse])
async def downgrade_subscription(
    payload: ChangePlanRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[SubscriptionResponse]:
    sub = await SubscriptionsService(db=db).downgrade_subscription(user_id, payload.plan_id)
    return ApiResponse.ok(sub)


@router.get("/me/usage", response_model=ApiResponse[UsageRecordResponse])
async def get_usage(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UsageRecordResponse]:
    usage = await SubscriptionsService(db=db).get_usage(user_id)
    return ApiResponse.ok(usage)
