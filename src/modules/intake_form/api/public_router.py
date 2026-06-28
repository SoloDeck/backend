from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.intake_form.application.service import IntakeFormService
from src.modules.intake_form.schemas.response import PublicIntakeFormConfigResponse
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/{share_token}/config",
    response_model=ApiResponse[PublicIntakeFormConfigResponse],
    summary="Get public intake form configuration",
    description=(
        "Returns the freelancer's intake form configuration for public display. "
        "Only visible fields (`is_visible=true`) are included. "
        "Used by the client-facing intake page to render the correct form fields. "
        "No authentication required — the `share_token` identifies the freelancer."
    ),
)
async def get_public_intake_config(
    share_token: str,
    db: DBSession,
) -> ApiResponse[PublicIntakeFormConfigResponse]:
    """Return the public-facing form config (visible fields only) for the given share token."""
    result = await IntakeFormService(db=db).get_public_config(share_token)
    return ApiResponse.ok(result)
