"""Auth application service."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from anyio import to_thread
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.modules.auth.schemas.request import (
    GoogleAuthRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestBody,
    RefreshRequest,
    RegisterRequest,
)
from src.modules.auth.schemas.response import AuthTokenResponse
from src.shared.exceptions.domain import AlreadyExistsError, AuthenticationError
from src.shared.security.passwords import hash_password, verify_password

# Reused across requests so the underlying HTTPS session (and Google's cached
# signing certificates) are kept warm — ID tokens are verified offline against
# these certs rather than via a per-login tokeninfo round-trip.
_google_transport_request = google_auth_requests.Request()


@dataclass
class AuthService:
    db: AsyncSession

    async def _issue_tokens(
        self, *, user_id: uuid.UUID, email: str, role: str
    ) -> AuthTokenResponse:
        from src.infrastructure.database.models import PlanModel, SubscriptionModel

        subscription_tier = "free"
        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is not None:
            plan = await self.db.scalar(
                select(PlanModel).where(PlanModel.id == sub.plan_id)
            )
            if plan is not None:
                subscription_tier = plan.slug

        now = datetime.now(UTC)
        access_expires = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        refresh_expires = now + timedelta(days=settings.jwt_refresh_token_expire_days)
        access_jti = str(uuid.uuid4())

        access_token = jwt.encode(
            {
                "sub": str(user_id),
                "email": email,
                "role": role,
                "subscription_tier": subscription_tier,
                "jti": access_jti,
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

    async def register(self, payload: RegisterRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import PlanModel, SubscriptionModel, UserModel

        existing = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == payload.email,
                UserModel.deleted_at.is_(None),
            )
        )
        if existing:
            raise AlreadyExistsError(f"Email '{payload.email}' is already registered")

        now = datetime.now(UTC)
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

        free_plan = await self.db.scalar(select(PlanModel).where(PlanModel.name == "Free"))
        if free_plan:
            subscription = SubscriptionModel(
                user_id=user_id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),
            )
            self.db.add(subscription)

        await self.db.flush()
        await self.db.refresh(user)

        return await self._issue_tokens(user_id=user_id, email=payload.email, role="freelancer")

    async def login(self, payload: LoginRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import UserModel

        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == payload.email,
                UserModel.deleted_at.is_(None),
            )
        )

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

        return await self._issue_tokens(user_id=user.id, email=user.email, role=user.role)

    async def refresh(self, payload: RefreshRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import UserModel

        try:
            claims = jwt.decode(
                payload.refresh_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError as err:
            raise AuthenticationError("Invalid or expired refresh token") from err

        if claims.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = uuid.UUID(claims["sub"])
        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
        )
        if user is None or user.status != "active":
            raise AuthenticationError("User not found or suspended")

        return await self._issue_tokens(user_id=user.id, email=user.email, role=user.role)

    async def logout(self, user_id: uuid.UUID, jti: str, expires_at: datetime) -> None:
        from src.infrastructure.database.models import TokenBlacklistModel

        entry = TokenBlacklistModel(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            blacklisted_at=datetime.now(UTC),
        )
        self.db.add(entry)
        await self.db.flush()

    @staticmethod
    def _google_audience(platform: str) -> str:
        """Return the expected ID token audience (client ID) for a platform."""
        return {
            "web": settings.google_web_client_id,
            "android": settings.google_android_client_id,
            "ios": settings.google_ios_client_id,
        }[platform]

    async def google_auth(self, payload: GoogleAuthRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import OAuthIdentityModel, UserModel

        audience = self._google_audience(payload.platform)

        # Offline cryptographic verification against Google's cached public certs.
        # verify_oauth2_token also enforces the audience and expiry; it is a blocking
        # call, so run it in a worker thread to avoid stalling the event loop.
        try:
            claims = await to_thread.run_sync(
                google_id_token.verify_oauth2_token,
                payload.id_token,
                _google_transport_request,
                audience,
            )
        except (ValueError, GoogleAuthError) as err:
            raise AuthenticationError("Invalid Google token") from err

        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise AuthenticationError("Invalid Google token issuer")

        google_sub = claims.get("sub")
        email = claims.get("email", "")
        name = claims.get("name", email)

        if not google_sub or not email:
            raise AuthenticationError("Incomplete Google token payload")

        oauth_identity = await self.db.scalar(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.provider == "google",
                OAuthIdentityModel.provider_sub == google_sub,
            )
        )

        if oauth_identity is not None:
            user = await self.db.scalar(
                select(UserModel).where(
                    UserModel.id == oauth_identity.user_id,
                    UserModel.deleted_at.is_(None),
                )
            )
            if user is None or user.status != "active":
                raise AuthenticationError("Account not available")
            return await self._issue_tokens(user_id=user.id, email=user.email, role=user.role)

        existing_user = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == email,
                UserModel.deleted_at.is_(None),
            )
        )

        if existing_user is not None:
            new_identity = OAuthIdentityModel(
                user_id=existing_user.id,
                provider="google",
                provider_sub=google_sub,
                provider_email=email,
            )
            self.db.add(new_identity)
            await self.db.flush()
            return await self._issue_tokens(
                user_id=existing_user.id, email=existing_user.email, role=existing_user.role
            )

        from src.infrastructure.database.models import PlanModel, SubscriptionModel

        now = datetime.now(UTC)
        new_user = UserModel(
            email=email,
            full_name=name,
            hashed_password=None,
            role="freelancer",
            status="active",
            locale="vi",
            timezone="Asia/Ho_Chi_Minh",
            notification_channel="email",
            theme="light",
        )
        self.db.add(new_user)
        await self.db.flush()
        await self.db.refresh(new_user)

        new_identity = OAuthIdentityModel(
            user_id=new_user.id,
            provider="google",
            provider_sub=google_sub,
            provider_email=email,
        )
        self.db.add(new_identity)

        free_plan = await self.db.scalar(select(PlanModel).where(PlanModel.name == "Free"))
        if free_plan:
            sub = SubscriptionModel(
                user_id=new_user.id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),
            )
            self.db.add(sub)

        await self.db.flush()

        return await self._issue_tokens(
            user_id=new_user.id, email=new_user.email, role=new_user.role
        )

    async def request_password_reset(self, payload: PasswordResetRequestBody) -> None:
        from src.infrastructure.database.models import (
            PasswordResetTokenModel,
            UserModel,
        )
        from src.shared.email.smtp import send_email

        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == payload.email,
                UserModel.deleted_at.is_(None),
            )
        )
        # Always return without revealing whether the email exists
        if user is None:
            return

        # Generate a 6-digit OTP and store its SHA-256 hash
        otp = f"{secrets.randbelow(1_000_000):06d}"
        token_hash = hashlib.sha256(otp.encode()).hexdigest()

        reset_token = PasswordResetTokenModel(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        self.db.add(reset_token)
        await self.db.flush()

        html = f"""
        <p>Xin chào <strong>{user.full_name}</strong>,</p>
        <p>Mã OTP đặt lại mật khẩu của bạn là:</p>
        <h2 style="letter-spacing:6px;">{otp}</h2>
        <p>Mã có hiệu lực trong <strong>15 phút</strong>.
        Vui lòng không chia sẻ mã này với bất kỳ ai.</p>
        <p>Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.</p>
        """
        plain = (
            f"Xin chào {user.full_name},\n\n"
            f"Mã OTP đặt lại mật khẩu của bạn là: {otp}\n\n"
            "Mã có hiệu lực trong 15 phút.\n"
            "Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này."
        )
        await send_email(
            to=user.email,
            subject="[SoloDesk] Mã OTP đặt lại mật khẩu",
            html=html,
            plain=plain,
        )

    async def confirm_password_reset(self, payload: PasswordResetConfirmRequest) -> None:
        from src.infrastructure.database.models import PasswordResetTokenModel, UserModel

        token_hash = hashlib.sha256(payload.otp.encode()).hexdigest()
        now = datetime.now(UTC)

        reset_token = await self.db.scalar(
            select(PasswordResetTokenModel).where(
                PasswordResetTokenModel.token_hash == token_hash,
                PasswordResetTokenModel.used_at.is_(None),
                PasswordResetTokenModel.expires_at > now,
            )
        )
        if reset_token is None:
            raise AuthenticationError("Invalid or expired reset token")

        reset_token.used_at = now

        user = await self.db.scalar(
            select(UserModel).where(UserModel.id == reset_token.user_id)
        )
        if user is not None:
            user.hashed_password = hash_password(payload.new_password)

        await self.db.flush()
