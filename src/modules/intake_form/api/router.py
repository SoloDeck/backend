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


@router.get("", response_model=ApiResponse[IntakeFormResponse])
async def get_intake_form(user_id: CurrentUserId, db: DBSession) -> ApiResponse[IntakeFormResponse]:
    result = await IntakeFormService(db=db).get_form_config(user_id)
    return ApiResponse.ok(result)


@router.put("", response_model=ApiResponse[IntakeFormResponse])
async def update_intake_form(
    user_id: CurrentUserId,
    payload: IntakeFormUpdateRequest,
    db: DBSession,
) -> ApiResponse[IntakeFormResponse]:
    result = await IntakeFormService(db=db).save_form_config(user_id, payload)
    return ApiResponse.ok(result)
