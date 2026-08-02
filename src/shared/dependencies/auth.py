"""FastAPI dependencies for JWT authentication and authorization."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select

from src.config.settings import settings
from src.infrastructure.database.models import TokenBlacklistModel, UserModel
from src.shared.dependencies.db import DBSession

_bearer = HTTPBearer(auto_error=True)


class TokenClaims(BaseModel):
    sub: str  # user_id (UUID string)
    email: str
    role: str  # freelancer | admin
    subscription_tier: str  # free | pro | agency
    jti: str  # JWT ID for blacklist check
    iat: int  # issued-at (unix timestamp) — checked against sessions_revoked_at


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: DBSession,
) -> TokenClaims:
    """Validate JWT and return decoded claims. Raises 401 on any failure.

    Also rejects tokens that were individually blacklisted (logout) or minted
    before an admin-forced session revocation (suspend, revoke_user_sessions) —
    signature/expiry alone can't catch either, since both leave the JWT itself
    untouched and valid until it naturally expires.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        claims = TokenClaims(**payload)
    except (JWTError, Exception) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or expired token"},
        ) from err

    blacklisted = await db.scalar(
        select(TokenBlacklistModel.id).where(TokenBlacklistModel.jti == claims.jti)
    )
    # Deliberately not filtering by deleted_at here — a soft-deleted account's own
    # endpoints already 404 downstream (see TestDeleteMe.test_deleted_user_cannot_fetch_profile);
    # this dependency only cares about admin-forced revocation (suspend/revoke_user_sessions).
    user = await db.scalar(select(UserModel).where(UserModel.id == uuid.UUID(claims.sub)))
    revoked = blacklisted is not None or user is None or user.status == "suspended"
    if not revoked and user.sessions_revoked_at is not None:
        revoked = claims.iat < user.sessions_revoked_at.timestamp()
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Token has been revoked"},
        )

    return claims


async def require_admin(
    claims: Annotated[TokenClaims, Depends(get_current_user)],
) -> TokenClaims:
    """Raises 403 if the authenticated user is not an admin."""
    if claims.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "Admin role required"},
        )
    return claims


# Convenience type aliases for api signatures
CurrentUser = Annotated[TokenClaims, Depends(get_current_user)]
AdminUser = Annotated[TokenClaims, Depends(require_admin)]


def current_user_id(claims: CurrentUser) -> uuid.UUID:
    return uuid.UUID(claims.sub)


CurrentUserId = Annotated[uuid.UUID, Depends(current_user_id)]
