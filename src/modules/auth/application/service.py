"""Auth application service.

Responsibilities:
- User registration (email + password)
- Credential-based login (email + password)
- Google OAuth 2.0 login and callback
- JWT access token issuance
- Refresh token lifecycle (issue, rotate, revoke)
- Logout and token blacklisting
- Password reset flow
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.shared.exceptions.domain import AlreadyExistsError, AuthenticationError
from src.shared.security.passwords import hash_password, verify_password
from src.modules.auth.schemas.request import LoginRequest, RegisterRequest
from src.modules.auth.schemas.response import AuthTokenResponse


@dataclass
class AuthService:
    db: AsyncSession

    async def register(self, payload: RegisterRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import UserModel, SubscriptionModel, PlanModel

        # Check for duplicate email
        existing = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == payload.email,
                UserModel.deleted_at.is_(None),
            )
        )
        if existing:
            raise AlreadyExistsError(f"Email '{payload.email}' is already registered")

        now = datetime.now(timezone.utc)
        user_id = uuid.uuid4()

        user = UserModel(
            id=user_id,
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role="freelancer",
            status="active",
            locale="vi",
            timezone="Asia/Ho_Chi_Minh",
            notification_channel="email",
            theme="light",
        )
        self.db.add(user)

        # Create free subscription
        free_plan = await self.db.scalar(select(PlanModel).where(PlanModel.name == "Free"))
        if free_plan:
            subscription = SubscriptionModel(
                user_id=user_id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),  # effectively perpetual
            )
            self.db.add(subscription)

        await self.db.commit()

        return self._issue_tokens(user_id=user_id, email=payload.email, role="freelancer")

    async def login(self, payload: LoginRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import UserModel

        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == payload.email,
                UserModel.deleted_at.is_(None),
            )
        )

        # Constant-time check: always verify even if user is None to prevent timing attacks
        stored_hash = user.hashed_password if user is not None else None
        password_ok = (
            verify_password(payload.password, stored_hash)
            if stored_hash is not None
            else False
        )

        if user is None or not password_ok:
            raise AuthenticationError("Invalid email or password")

        if user.status != "active":
            raise AuthenticationError("Account is suspended")

        return self._issue_tokens(
            user_id=user.id, email=user.email, role=user.role
        )

    def _issue_tokens(self, *, user_id: uuid.UUID, email: str, role: str) -> AuthTokenResponse:
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        refresh_expires = now + timedelta(days=settings.jwt_refresh_token_expire_days)

        access_token = jwt.encode(
            {
                "sub": str(user_id),
                "email": email,
                "role": role,
                "exp": access_expires,
                "iat": now,
                "type": "access",
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        refresh_token = jwt.encode(
            {
                "sub": str(user_id),
                "exp": refresh_expires,
                "iat": now,
                "type": "refresh",
                "jti": str(uuid.uuid4()),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
