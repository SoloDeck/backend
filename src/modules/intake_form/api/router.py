from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.intake_form.application.service import IntakeFormService
from src.modules.intake_form.schemas.request import IntakeFormUpdateRequest
from src.modules.intake_form.schemas.response import IntakeFormResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "",
    response_model=ApiResponse[IntakeFormResponse],
    summary="Get intake form configuration",
    description=(
        "Returns the authenticated freelancer's intake form configuration including all fields. "
        "If no configuration has been saved yet, returns the default 7-field form. "
        "The `share_url` in the response can be shared publicly with potential clients."
    ),
)
async def get_intake_form(user_id: CurrentUserId, db: DBSession) -> ApiResponse[IntakeFormResponse]:
    """Return the current intake form config, falling back to defaults when not yet configured."""
    result = await IntakeFormService(db=db).get_form_config(user_id)
    return ApiResponse.ok(result)


@router.put(
    "",
    response_model=ApiResponse[IntakeFormResponse],
    summary="Save intake form configuration",
    description=(
        "Creates or fully replaces the authenticated freelancer's intake form configuration. "
        "The `fields` array replaces all existing fields — omitting a field removes it. "
        "At least the `name` and `inquiry_text` field keys should be included for intake submissions to work correctly."
    ),
)
async def update_intake_form(
    user_id: CurrentUserId,
    payload: IntakeFormUpdateRequest,
    db: DBSession,
) -> ApiResponse[IntakeFormResponse]:
    """Upsert the intake form config and replace all fields with the ones provided in the request."""
    result = await IntakeFormService(db=db).save_form_config(user_id, payload)
    return ApiResponse.ok(result)
