from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.auth.application.service import AuthService
from src.modules.auth.schemas.request import RegisterRequest
from src.modules.auth.schemas.response import AuthTokenResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new freelancer account",
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthTokenResponse:
    return await AuthService(db=db).register(payload)


# POST /login
# POST /refresh
# POST /logout
# GET  /google
# GET  /google/callback
# POST /password-reset/request
# POST /password-reset/confirm
