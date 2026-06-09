"""Auth application service."""

import hashlib
import secrets
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import httpx
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

    async def google_auth(self, payload: GoogleAuthRequest) -> AuthTokenResponse:
        from src.infrastructure.database.models import OAuthIdentityModel, UserModel

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://www.googleapis.com/oauth2/v3/tokeninfo?id_token={payload.id_token}"
            )

        if resp.status_code != 200:
            raise AuthenticationError("Invalid Google token")

        token_info = resp.json()
        aud = token_info.get("aud", "")
        if aud != settings.google_client_id:
            raise AuthenticationError("Google token audience mismatch")

        google_sub = token_info.get("sub")
        email = token_info.get("email", "")
        name = token_info.get("name", email)

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
        from src.infrastructure.database.models import UserModel, PasswordResetTokenModel
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
        <p>Mã có hiệu lực trong <strong>15 phút</strong>. Vui lòng không chia sẻ mã này với bất kỳ ai.</p>
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

    @staticmethod
    def get_google_auth_url() -> str:
        """Build the Google OAuth 2.0 authorization URL and return it.

        A short-lived signed JWT is used as the ``state`` parameter to prevent
        CSRF without requiring server-side session storage.
        """
        state = jwt.encode(
            {
                "type": "oauth_state",
                "nonce": secrets.token_hex(16),
                "exp": datetime.now(UTC) + timedelta(minutes=10),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    async def google_oauth_callback(self, code: str, state: str) -> AuthTokenResponse:
        """Exchange the authorization *code* from Google for application tokens.

        Verifies the ``state`` JWT to guard against CSRF, exchanges the code
        for a Google ID token, then delegates to the existing ``google_auth``
        upsert logic.
        """
        try:
            claims = jwt.decode(
                state,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError as err:
            raise AuthenticationError("Invalid or expired OAuth state parameter") from err

        if claims.get("type") != "oauth_state":
            raise AuthenticationError("Malformed OAuth state parameter")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        if resp.status_code != 200:
            raise AuthenticationError("Failed to exchange Google authorization code")

        token_data = resp.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise AuthenticationError("Google token exchange response missing id_token")

        return await self.google_auth(GoogleAuthRequest(id_token=id_token))
