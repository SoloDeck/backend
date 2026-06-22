"""Proposals API api."""

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.proposals.application.service import ProposalsService
from src.modules.proposals.schemas.request import AiProposalRequest, ProposalRequest, ProposalStatusRequest
from src.modules.proposals.schemas.response import ProposalResponse
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("/ai-generate", response_model=ApiResponse[ProposalResponse], status_code=201)
async def ai_generate_proposal(
    payload: AiProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    from google import genai
    from src.ai.proposal_generator.application.service import ProposalGenerationService
    from src.ai.proposal_generator.schemas.ProposalGenerationInput import ProposalGenerationInput
    from src.config.settings import settings

    gen_input = ProposalGenerationInput(
        client_name=payload.client_name,
        company_name=payload.company_name,
        project_type=payload.project_type,
        project_description=payload.project_description,
        estimated_scope=payload.estimated_scope,
        budget=payload.budget,
        urgency=payload.urgency,
        service_category=payload.service_category,
        pricing_tier=payload.pricing_tier,
        freelancer_name=payload.freelancer_name,
    )
    client = genai.Client(api_key=settings.gemini_api_key)
    svc = ProposalGenerationService(client=client)
    content = await asyncio.to_thread(svc.generate, gen_input)

    proposal = await ProposalsService(db=db).create(
        user_id,
        ProposalRequest(deal_id=payload.deal_id, content=content.model_dump()),
        ai_generated=True,
    )
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.post("", response_model=ApiResponse[ProposalResponse], status_code=201)
async def create_proposal(
    payload: ProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).create(user_id, payload)
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.get("", response_model=PaginatedResponse[ProposalResponse])
async def list_proposals(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(default=None, description="Filter by status: draft, sent, accepted, rejected, expired"),
    deal_id: uuid.UUID | None = Query(default=None, description="Filter by deal"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[ProposalResponse]:
    proposals, total = await ProposalsService(db=db).list_all(
        user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [ProposalResponse.model_validate(p) for p in proposals],
        total=total, page=page, page_size=page_size,
    )


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


@router.post("/{proposal_id}/generate", response_model=ApiResponse[ProposalResponse])
async def ai_generate_proposal_content(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).generate_content(user_id, proposal_id, ai)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.post("/{proposal_id}/send", response_model=ApiResponse[ProposalResponse])
async def send_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).transition_status(user_id, proposal_id, "sent")
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
