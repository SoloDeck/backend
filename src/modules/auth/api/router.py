"""Auth API api."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.database.session import get_db_session
from src.modules.auth.application.service import AuthService
from src.modules.auth.schemas.request import (
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
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
from src.shared.rate_limit.auth_guards import (
    chan_nhip_dang_nhap,
    chan_nhip_go_ma,
    chan_nhip_xin_ma,
)
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
    request: Request,
) -> ApiResponse[AuthTokenResponse]:
    # Chặn TRƯỚC khi đụng tới DB và trước khi băm mật khẩu: mỗi lượt đăng nhập với email
    # có thật tiêu 64 MiB RAM cho Argon2id, nên để lọt vào tới đó là đã tốn rồi.  #Huynh
    chan_nhip_dang_nhap(request, payload.email)
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
    payload: LogoutRequest | None = None,
) -> ApiResponse[MessageResponse]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    await AuthService(db=db).logout(
        user_id=uuid.UUID(current_user.sub),
        jti=current_user.jti,
        expires_at=expires_at,
        refresh_token=payload.refresh_token if payload else None,
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
    request: Request,
) -> ApiResponse[MessageResponse]:
    # Mỗi lượt lọt qua đây là một lá thư thật rời hệ thống và một suất trong hạn mức gửi
    # hằng ngày. Hạn mức cháy là cả hệ thống mất email tới hôm sau.  #Huynh
    chan_nhip_xin_ma(request, payload.email)
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
    request: Request,
) -> ApiResponse[MessageResponse]:
    # Lớp thứ hai, sau bộ đếm `attempts` nằm trên chính bản ghi mã: `attempts` chặn người
    # dò một tài khoản, chốt này chặn người rải mã qua hàng loạt tài khoản.  #Huynh
    chan_nhip_go_ma(request)
    await AuthService(db=db).confirm_password_reset(payload)
    return ApiResponse.ok(MessageResponse(detail="Password reset successfully"))
