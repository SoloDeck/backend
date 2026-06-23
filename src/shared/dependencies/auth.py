"""FastAPI dependencies for JWT authentication and authorization."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from src.config.settings import settings

_bearer = HTTPBearer(auto_error=True)


class TokenClaims(BaseModel):
    sub: str          # user_id (UUID string)
    email: str
    role: str         # freelancer | admin
    subscription_tier: str  # free | pro | agency
    jti: str          # JWT ID for blacklist check


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> TokenClaims:
    """Validate JWT and return decoded claims. Raises 401 on any failure."""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenClaims(**payload)
    except (JWTError, Exception) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Invalid or expired token"},
        ) from err


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
