"""Auth API router."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.database.session import get_db_session
from src.modules.auth.application.service import AuthService
from src.modules.auth.schemas.request import (
    GoogleAuthRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestBody,
    RefreshRequest,
    RegisterRequest,
)
from src.modules.auth.schemas.response import (
    AuthTokenResponse,
    ClientConfigResponse,
    MessageResponse,
)
from src.shared.dependencies.auth import CurrentUser
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/config",
    response_model=ApiResponse[ClientConfigResponse],
    summary="Get public configuration settings",
)
async def get_client_config() -> ApiResponse[ClientConfigResponse]:
    return ApiResponse.ok(
        ClientConfigResponse(
            app_env=settings.app_env,
            google_web_client_id=settings.google_web_client_id,
        )
    )


@router.post(
    "/register",
    response_model=ApiResponse[AuthTokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new freelancer account",
)
async def register(
    payload: RegisterRequest,
    db: DBSession,
) -> ApiResponse[AuthTokenResponse]:
    result = await AuthService(db=db).register(payload)
    return ApiResponse.created(result)


@router.post(
    "/login",
    response_model=ApiResponse[AuthTokenResponse],
    summary="Login with email and password",
)
async def login(
    payload: LoginRequest,
    db: DBSession,
) -> ApiResponse[AuthTokenResponse]:
    result = await AuthService(db=db).login(payload)
    return ApiResponse.ok(result)


@router.post(
    "/refresh",
    response_model=ApiResponse[AuthTokenResponse],
    summary="Refresh access token",
)
async def refresh(
    payload: RefreshRequest,
    db: DBSession,
) -> ApiResponse[AuthTokenResponse]:
    result = await AuthService(db=db).refresh(payload)
    return ApiResponse.ok(result)


@router.post(
    "/logout",
    response_model=ApiResponse[MessageResponse],
    summary="Logout and blacklist current token",
)
async def logout(
    current_user: CurrentUser,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    await AuthService(db=db).logout(
        user_id=uuid.UUID(current_user.sub),
        jti=current_user.jti,
        expires_at=expires_at,
    )
    return ApiResponse.ok(MessageResponse(detail="Logged out successfully"))


@router.post(
    "/google",
    response_model=ApiResponse[AuthTokenResponse],
    summary="Authenticate with Google ID token",
)
async def google_auth(
    payload: GoogleAuthRequest,
    db: DBSession,
) -> ApiResponse[AuthTokenResponse]:
    result = await AuthService(db=db).google_auth(payload)
    return ApiResponse.ok(result)


@router.post(
    "/password-reset/request",
    response_model=ApiResponse[MessageResponse],
    summary="Request a password reset token",
)
async def password_reset_request(
    payload: PasswordResetRequestBody,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await AuthService(db=db).request_password_reset(payload)
    return ApiResponse.ok(MessageResponse(detail="Nếu email tồn tại, mã OTP đã được gửi"))


@router.post(
    "/password-reset/confirm",
    response_model=ApiResponse[MessageResponse],
    summary="Confirm password reset with token",
)
async def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await AuthService(db=db).confirm_password_reset(payload)
    return ApiResponse.ok(MessageResponse(detail="Password reset successfully"))
