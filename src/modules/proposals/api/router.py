"""Proposals API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.proposals.application.service import ProposalsService
from src.modules.proposals.schemas.request import ProposalRequest, ProposalStatusRequest
from src.modules.proposals.schemas.response import ProposalResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[ProposalResponse], status_code=201)
async def create_proposal(
    payload: ProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).create(user_id, payload)
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.get("", response_model=ApiResponse[list[ProposalResponse]])
async def list_proposals(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(default=None, description="Filter by status: draft, sent, accepted, rejected, expired"),
) -> ApiResponse[list[ProposalResponse]]:
    proposals = await ProposalsService(db=db).list_all(user_id, status=status)
    return ApiResponse.ok([ProposalResponse.model_validate(p) for p in proposals])


@router.get("/{proposal_id}", response_model=ApiResponse[ProposalResponse])
async def get_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).get_one(user_id, proposal_id)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.patch("/{proposal_id}", response_model=ApiResponse[ProposalResponse])
async def update_proposal(
    proposal_id: uuid.UUID,
    payload: ProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).update(user_id, proposal_id, payload)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.patch("/{proposal_id}/status", response_model=ApiResponse[ProposalResponse])
async def transition_proposal_status(
    proposal_id: uuid.UUID,
    payload: ProposalStatusRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).transition_status(user_id, proposal_id, payload.status)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.delete("/{proposal_id}", response_model=ApiResponse[MsgResp])
async def delete_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ProposalsService(db=db).delete(user_id, proposal_id)
    return ApiResponse.ok(MsgResp(detail="Proposal deleted"))
