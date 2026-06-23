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
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.database.models import (
    OAuthIdentityModel,
    PasswordResetTokenModel,
    SubscriptionModel,
    TokenBlacklistModel,
    UserModel,
)
from src.modules.auth.infrastructure.repository import AuthRepository
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
    repo: AuthRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AuthRepository(self.db)

    async def _issue_tokens(
        self, *, user_id: uuid.UUID, email: str, role: str
    ) -> AuthTokenResponse:
        subscription_tier = "free"
        sub = await self.repo.get_subscription(user_id)
        if sub is not None:
            plan = await self.repo.get_plan(sub.plan_id)
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
        existing = await self.repo.get_user_by_email(payload.email)
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
            intake_share_token=secrets.token_urlsafe(32),
        )
        await self.repo.add_user(user)

        free_plan = await self.repo.get_free_plan()
        if free_plan:
            subscription = SubscriptionModel(
                user_id=user_id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),
            )
            await self.repo.add_subscription(subscription)

        await self.repo.flush()
        await self.repo.refresh(user)

        return await self._issue_tokens(user_id=user_id, email=payload.email, role="freelancer")

    async def login(self, payload: LoginRequest) -> AuthTokenResponse:
        user = await self.repo.get_user_by_email(payload.email)

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
        user = await self.repo.get_user_by_id(user_id)
        if user is None or user.status != "active":
            raise AuthenticationError("User not found or suspended")

        return await self._issue_tokens(user_id=user.id, email=user.email, role=user.role)

    async def logout(self, user_id: uuid.UUID, jti: str, expires_at: datetime) -> None:
        entry = TokenBlacklistModel(
            jti=jti,
            user_id=user_id,
            expires_at=expires_at,
            blacklisted_at=datetime.now(UTC),
        )
        await self.repo.add_token_blacklist(entry)
        await self.repo.flush()

    @staticmethod
    def _allowed_audiences(platform: str) -> tuple[str, ...]:
        """Accepted ID-token audiences for the platform.

        google_sign_in (android/ios) mints the token for the web client when
        serverClientId is set, but may use the native client id otherwise — accept
        both. Web (GIS) always uses the web client. All are this app's own OAuth
        clients, so accepting any of them is safe.
        """
        native = {
            "web": (),
            "android": (settings.google_android_client_id,),
            "ios": (settings.google_ios_client_id,),
        }[platform]
        return tuple(a for a in (settings.google_web_client_id, *native) if a)

    async def google_auth(self, payload: GoogleAuthRequest) -> AuthTokenResponse:
        allowed_audiences = self._allowed_audiences(payload.platform)

        # Offline cryptographic verification against Google's cached public certs
        # (signature + issuer + expiry). The audience is then checked against the
        # platform's accepted set below. Blocking call — run in a worker thread.
        try:
            claims = await to_thread.run_sync(
                google_id_token.verify_oauth2_token,
                payload.id_token,
                _google_transport_request,
            )
        except (ValueError, GoogleAuthError) as err:
            raise AuthenticationError("Invalid Google token") from err

        if claims.get("aud") not in allowed_audiences:
            raise AuthenticationError("Google token audience mismatch")

        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise AuthenticationError("Invalid Google token issuer")

        google_sub = claims.get("sub")
        email = claims.get("email", "")
        name = claims.get("name", email)

        if not google_sub or not email:
            raise AuthenticationError("Incomplete Google token payload")

        oauth_identity = await self.repo.get_oauth_identity("google", google_sub)

        if oauth_identity is not None:
            user = await self.repo.get_user_by_id(oauth_identity.user_id)
            if user is None or user.status != "active":
                raise AuthenticationError("Account not available")
            return await self._issue_tokens(user_id=user.id, email=user.email, role=user.role)

        existing_user = await self.repo.get_user_by_email(email)

        if existing_user is not None:
            new_identity = OAuthIdentityModel(
                user_id=existing_user.id,
                provider="google",
                provider_sub=google_sub,
                provider_email=email,
            )
            await self.repo.add_oauth_identity(new_identity)
            await self.repo.flush()
            return await self._issue_tokens(
                user_id=existing_user.id, email=existing_user.email, role=existing_user.role
            )

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
            intake_share_token=secrets.token_urlsafe(32),
        )
        await self.repo.add_user(new_user)
        await self.repo.flush()
        await self.repo.refresh(new_user)

        new_identity = OAuthIdentityModel(
            user_id=new_user.id,
            provider="google",
            provider_sub=google_sub,
            provider_email=email,
        )
        await self.repo.add_oauth_identity(new_identity)

        free_plan = await self.repo.get_free_plan()
        if free_plan:
            sub = SubscriptionModel(
                user_id=new_user.id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),
            )
            await self.repo.add_subscription(sub)

        await self.repo.flush()

        return await self._issue_tokens(
            user_id=new_user.id, email=new_user.email, role=new_user.role
        )

    async def request_password_reset(self, payload: PasswordResetRequestBody) -> None:
        from src.shared.email.smtp import send_email

        user = await self.repo.get_user_by_email(payload.email)
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
        await self.repo.add_reset_token(reset_token)
        await self.repo.flush()

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
        token_hash = hashlib.sha256(payload.otp.encode()).hexdigest()
        now = datetime.now(UTC)

        reset_token = await self.repo.get_reset_token(token_hash, now)
        if reset_token is None:
            raise AuthenticationError("Invalid or expired reset token")

        reset_token.used_at = now

        user = await self.repo.get_user_by_id(reset_token.user_id)
        if user is not None:
            user.hashed_password = hash_password(payload.new_password)

        await self.repo.flush()
