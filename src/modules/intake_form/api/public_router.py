from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from fastapi import Depends

from src.infrastructure.database.session import get_db_session
from src.modules.intake_form.application.service import IntakeFormService
from src.modules.intake_form.schemas.response import PublicIntakeFormConfigResponse
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/{share_token}/config", response_model=ApiResponse[PublicIntakeFormConfigResponse])
async def get_public_intake_config(
    share_token: str,
    db: DBSession,
) -> ApiResponse[PublicIntakeFormConfigResponse]:
    result = await IntakeFormService(db=db).get_public_config(share_token)
    return ApiResponse.ok(result)
