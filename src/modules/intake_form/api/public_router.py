from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.intake_form.application.service import IntakeFormService
from src.modules.intake_form.schemas.response import (
    PublicIntakeFormConfigResponse,
    PublicProfileResponse,
)
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


@router.get(
    "/{share_token}/profile",
    response_model=ApiResponse[PublicProfileResponse],
    summary="Get the freelancer's public share profile",
    description=(
        "Returns the freelancer's introduction page that sits in front of their intake "
        "form. Identified **only** by `share_token` — there is no lookup by user id, so "
        "profiles cannot be enumerated or browsed. No authentication required."
    ),
)
async def get_public_profile(
    share_token: str,
    db: DBSession,
) -> ApiResponse[PublicProfileResponse]:
    """Return the freelancer introduction shown above the intake form for this share token."""
    result = await IntakeFormService(db=db).get_public_profile(share_token)
    return ApiResponse.ok(result)
