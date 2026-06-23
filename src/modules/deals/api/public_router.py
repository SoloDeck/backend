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


@router.post(
    "/{share_token}",
    response_model=ApiResponse[PublicIntakeResponse],
    status_code=201,
    summary="Submit a public intake request",
    description=(
        "Allows a potential client to submit a project inquiry directly to a freelancer. "
        "The `share_token` identifies the freelancer who owns the intake form. "
        "Required fields are validated against the freelancer's saved form configuration. "
        "On success, a new Deal is created in the freelancer's CRM and AI lead scoring is triggered asynchronously. "
        "No authentication required."
    ),
)
async def submit_public_intake(
    share_token: str,
    payload: PublicIntakeRequest,
    db: DBSession,
) -> ApiResponse[PublicIntakeResponse]:
    """Validate required fields against the form config, then create a Deal from the intake submission."""
    await IntakeFormService(db=db).validate_submission(share_token, payload)
    intake = await DealsService(db=db).create_public_intake(share_token, payload)
    return ApiResponse.created(PublicIntakeResponse.model_validate(intake))
