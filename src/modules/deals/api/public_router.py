"""Public deal-intake endpoint — no authentication required.

Mounted at `/api/v1/intake`. A client self-submits a lead via the owner's
hard-to-guess share token; the owner is resolved from that token alone.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import PublicIntakeRequest
from src.modules.deals.schemas.response import PublicIntakeResponse
from src.modules.intake_form.application.service import IntakeFormService
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/{share_token}", response_model=ApiResponse[PublicIntakeResponse], status_code=201)
async def submit_public_intake(
    share_token: str,
    payload: PublicIntakeRequest,
    db: DBSession,
) -> ApiResponse[PublicIntakeResponse]:
    await IntakeFormService(db=db).validate_submission(share_token, payload)
    intake = await DealsService(db=db).create_public_intake(share_token, payload)
    return ApiResponse.created(PublicIntakeResponse.model_validate(intake))
