"""Public proposal endpoints — no authentication required."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.proposals.application.service import ProposalsService
from src.modules.proposals.schemas.request import ProposalRespondRequest
from src.modules.proposals.schemas.response import PublicProposalResponse
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/{share_token}", response_model=ApiResponse[PublicProposalResponse])
async def get_public_proposal(
    share_token: str, db: DBSession
) -> ApiResponse[PublicProposalResponse]:
    proposal = await ProposalsService(db=db).get_public_view(share_token)
    return ApiResponse.ok(PublicProposalResponse.model_validate(proposal))


@router.post("/{share_token}/respond", response_model=ApiResponse[PublicProposalResponse])
async def respond_to_proposal(
    share_token: str, payload: ProposalRespondRequest, db: DBSession
) -> ApiResponse[PublicProposalResponse]:
    proposal = await ProposalsService(db=db).respond_via_share_token(
        share_token, payload.decision, payload.note
    )
    return ApiResponse.ok(PublicProposalResponse.model_validate(proposal))
