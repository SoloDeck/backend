"""Deals API router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import DealRequest, DealStageRequest
from src.modules.deals.schemas.response import DealResponse
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[DealResponse], status_code=201)
async def create_deal(
    payload: DealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).create(user_id, payload)
    return ApiResponse.created(DealResponse.model_validate(deal))


@router.get("", response_model=ApiResponse[list[DealResponse]])
async def list_deals(
    user_id: CurrentUserId,
    db: DBSession,
    title: str | None = Query(default=None, description="Search by title (case-insensitive, partial match)"),
    stage: str | None = Query(default=None, description="Filter by stage: new_lead, qualified, proposal_sent, in_negotiation, active, completed_and_billed, lost"),
) -> ApiResponse[list[DealResponse]]:
    deals = await DealsService(db=db).list_all(user_id, title=title, stage=stage)
    return ApiResponse.ok([DealResponse.model_validate(d) for d in deals])


@router.get("/{deal_id}", response_model=ApiResponse[DealResponse])
async def get_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).get_one(user_id, deal_id)
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.patch("/{deal_id}", response_model=ApiResponse[DealResponse])
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).update(user_id, deal_id, payload)
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.delete("/{deal_id}", response_model=ApiResponse[MsgResp])
async def delete_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await DealsService(db=db).delete(user_id, deal_id)
    return ApiResponse.ok(MsgResp(detail="Deal deleted"))


@router.post("/{deal_id}/stage", response_model=ApiResponse[DealResponse])
async def transition_stage(
    deal_id: uuid.UUID,
    payload: DealStageRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).transition_stage(user_id, deal_id, payload)
    return ApiResponse.ok(DealResponse.model_validate(deal))

@router.post("/intakes/{intake_id}/qualify")
async def qualify_deal_intake(
    intake_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
):
    result = await DealsService(
        db=db,
        ai_facade=ai,
    ).qualify_deal_intake(
        user_id,
        intake_id,
    )

    return ApiResponse.ok(result)
