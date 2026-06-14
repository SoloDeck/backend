"""Unit tests for AuthService.

All DB calls are mocked via AsyncMock — no real database required.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import settings
from src.modules.auth.application.service import AuthService
from src.modules.auth.schemas.request import (
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
)
from src.shared.exceptions.domain import AlreadyExistsError, AuthenticationError
from src.shared.security.passwords import hash_password

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    status: str = "active",
    role: str = "freelancer",
    email: str = "user@example.com",
    full_name: str = "Test User",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password=hash_password("Test@1234!"),
        status=status,
        role=role,
    )


def _make_plan() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="Free")


def _mock_db(scalar_returns: list) -> AsyncMock:
    db = AsyncMock()
    db.scalar.side_effect = scalar_returns
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# TestRegister
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_success_returns_token_response(self) -> None:
        db = _mock_db([None, _make_plan(), None])  # user check, free plan, issue_tokens sub
        service = AuthService(db=db)
        result = await service.register(
            RegisterRequest(email="new@example.com", password="Test@1234!", full_name="New User")
        )
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "Bearer"

    async def test_creates_user_and_subscription_when_free_plan_exists(self) -> None:
        free_plan = _make_plan()
        db = _mock_db([None, free_plan, None]) # user check, free plan, issue_tokens sub
        service = AuthService(db=db)
        await service.register(
            RegisterRequest(email="new@example.com", password="Test@1234!", full_name="New User")
        )
        assert db.add.call_count == 2

    async def test_creates_only_user_when_no_free_plan(self) -> None:
        db = _mock_db([None, None, None]) # user check, free plan, issue_tokens sub
        service = AuthService(db=db)
        result = await service.register(
            RegisterRequest(email="new@example.com", password="Test@1234!", full_name="New User")
        )
        assert db.add.call_count == 1
        assert result.access_token

    async def test_duplicate_email_raises_already_exists(self) -> None:
        db = _mock_db([_make_user()])
        service = AuthService(db=db)
        with pytest.raises(AlreadyExistsError):
            await service.register(
                RegisterRequest(
                    email="existing@example.com", password="Test@1234!", full_name="Dup"
                )
            )


# ---------------------------------------------------------------------------
# TestLogin
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_success_returns_token_response(self) -> None:
        user = _make_user()
        db = _mock_db([user, None]) # login user, issue_tokens sub
        service = AuthService(db=db)
        result = await service.login(
            LoginRequest(email=user.email, password="Test@1234!")
        )
        assert result.access_token
        assert result.token_type == "Bearer"

    async def test_wrong_password_raises_authentication_error(self) -> None:
        user = _make_user()
        db = _mock_db([user])
        service = AuthService(db=db)
        with pytest.raises(AuthenticationError):
            await service.login(LoginRequest(email=user.email, password="wrongpass"))

    async def test_user_not_found_raises_authentication_error(self) -> None:
        db = _mock_db([None])
        service = AuthService(db=db)
        with pytest.raises(AuthenticationError):
            await service.login(LoginRequest(email="ghost@example.com", password="Test@1234!"))

    async def test_suspended_account_raises_authentication_error(self) -> None:
        user = _make_user(status="suspended")
        db = _mock_db([user])
        service = AuthService(db=db)
        with pytest.raises(AuthenticationError) as exc_info:
            await service.login(LoginRequest(email=user.email, password="Test@1234!"))
        assert "suspended" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# TestGoogleAuth
# ---------------------------------------------------------------------------

from unittest.mock import patch as _patch  # noqa: E402

_VERIFY = "src.modules.auth.application.service.google_id_token.verify_oauth2_token"
_WEB_AUD = "web-test-id.apps.googleusercontent.com"
_ANDROID_AUD = "android-test-id.apps.googleusercontent.com"
_IOS_AUD = "ios-test-id.apps.googleusercontent.com"
_VALID_CLAIMS = {
    "iss": "accounts.google.com",
    "aud": _WEB_AUD,
    "sub": "google-sub-123",
    "email": "g@example.com",
    "name": "G User",
}


def _identity() -> SimpleNamespace:
    return SimpleNamespace(
        user_id=uuid.uuid4(), provider="google", provider_sub="google-sub-123"
    )


class TestGoogleAuth:
    @pytest.fixture(autouse=True)
    def _configure_audiences(self):
        with (
            _patch.object(settings, "google_web_client_id", _WEB_AUD),
            _patch.object(settings, "google_android_client_id", _ANDROID_AUD),
            _patch.object(settings, "google_ios_client_id", _IOS_AUD),
        ):
            yield

    @_patch(_VERIFY)
    async def test_offline_verification_is_used(self, mock_verify: MagicMock) -> None:
        """Happy path runs through offline cert verification — no tokeninfo HTTP call."""
        mock_verify.return_value = dict(_VALID_CLAIMS)
        db = _mock_db([_identity(), _make_user(), None])
        service = AuthService(db=db)
        result = await service.google_auth(
            GoogleAuthRequest(id_token="tok", platform="web")
        )
        assert result.access_token
        mock_verify.assert_called_once()

    @_patch(_VERIFY)
    async def test_audience_accepts_web_or_native_client_id(
        self, mock_verify: MagicMock
    ) -> None:
        # Each platform accepts the web/server client id; mobile additionally
        # accepts its native client id (in case serverClientId is not set).
        accepted = [
            ("web", _WEB_AUD),
            ("android", _WEB_AUD),
            ("android", _ANDROID_AUD),
            ("ios", _WEB_AUD),
            ("ios", _IOS_AUD),
        ]
        for platform, aud in accepted:
            mock_verify.reset_mock()
            mock_verify.return_value = {**_VALID_CLAIMS, "aud": aud}
            db = _mock_db([_identity(), _make_user(), None])
            result = await AuthService(db=db).google_auth(
                GoogleAuthRequest(id_token="tok", platform=platform)
            )
            assert result.access_token, (platform, aud)

    @_patch(_VERIFY)
    async def test_audience_rejects_foreign_client_id(
        self, mock_verify: MagicMock
    ) -> None:
        mock_verify.return_value = {**_VALID_CLAIMS, "aud": "attacker.apps.googleusercontent.com"}
        with pytest.raises(AuthenticationError):
            await AuthService(db=_mock_db([])).google_auth(
                GoogleAuthRequest(id_token="tok", platform="android")
            )

    @_patch(_VERIFY)
    async def test_android_native_aud_rejected_on_ios_platform(
        self, mock_verify: MagicMock
    ) -> None:
        # An android-minted token presented as ios must not pass (cross-platform).
        mock_verify.return_value = {**_VALID_CLAIMS, "aud": _ANDROID_AUD}
        with pytest.raises(AuthenticationError):
            await AuthService(db=_mock_db([])).google_auth(
                GoogleAuthRequest(id_token="tok", platform="ios")
            )

    @_patch(_VERIFY)
    async def test_invalid_token_raises(self, mock_verify: MagicMock) -> None:
        mock_verify.side_effect = ValueError("bad signature")
        service = AuthService(db=_mock_db([]))
        with pytest.raises(AuthenticationError):
            await service.google_auth(GoogleAuthRequest(id_token="bad", platform="web"))

    @_patch(_VERIFY)
    async def test_wrong_issuer_raises(self, mock_verify: MagicMock) -> None:
        mock_verify.return_value = {**_VALID_CLAIMS, "iss": "evil.example.com"}
        service = AuthService(db=_mock_db([]))
        with pytest.raises(AuthenticationError):
            await service.google_auth(GoogleAuthRequest(id_token="tok", platform="web"))

    @_patch(_VERIFY)
    async def test_new_user_created_with_free_plan(self, mock_verify: MagicMock) -> None:
        mock_verify.return_value = dict(_VALID_CLAIMS)
        # identity None, email None, free plan, issue_tokens sub
        db = _mock_db([None, None, _make_plan(), None])
        service = AuthService(db=db)
        result = await service.google_auth(
            GoogleAuthRequest(id_token="tok", platform="ios")
        )
        assert result.access_token
        assert db.add.call_count == 3  # user + identity + subscription

    @_patch(_VERIFY)
    async def test_existing_email_links_identity(self, mock_verify: MagicMock) -> None:
        mock_verify.return_value = dict(_VALID_CLAIMS)
        # identity None, existing email user, issue_tokens sub
        db = _mock_db([None, _make_user(), None])
        service = AuthService(db=db)
        result = await service.google_auth(
            GoogleAuthRequest(id_token="tok", platform="web")
        )
        assert result.access_token
        assert db.add.call_count == 1  # only the linked identity


# ---------------------------------------------------------------------------
# TestPasswordReset
# ---------------------------------------------------------------------------

from unittest.mock import patch
from src.modules.auth.schemas.request import PasswordResetRequestBody, PasswordResetConfirmRequest

class TestPasswordReset:
    @patch("src.shared.email.smtp.send_email")
    async def test_request_reset_success(self, mock_send_email: AsyncMock) -> None:
        user = _make_user()
        db = _mock_db([user])
        service = AuthService(db=db)
        await service.request_password_reset(PasswordResetRequestBody(email=user.email))
        
        assert db.add.call_count == 1  # reset_token
        db.flush.assert_called_once()
        mock_send_email.assert_called_once()
        
    @patch("src.shared.email.smtp.send_email")
    async def test_request_reset_user_not_found_returns_silently(self, mock_send_email: AsyncMock) -> None:
        db = _mock_db([None])
        service = AuthService(db=db)
        await service.request_password_reset(PasswordResetRequestBody(email="ghost@example.com"))
        
        db.add.assert_not_called()
        mock_send_email.assert_not_called()

    async def test_confirm_reset_success(self) -> None:
        token_model = SimpleNamespace(user_id=uuid.uuid4(), used_at=None)
        user = _make_user()
        db = _mock_db([token_model, user])
        service = AuthService(db=db)
        
        await service.confirm_password_reset(
            PasswordResetConfirmRequest(otp="123456", new_password="NewPassword@123!")
        )
        
        assert token_model.used_at is not None
        assert user.hashed_password is not None
        db.flush.assert_called_once()

    async def test_confirm_reset_invalid_token_raises_error(self) -> None:
        db = _mock_db([None])
        service = AuthService(db=db)
        
        with pytest.raises(AuthenticationError, match="Invalid or expired reset token"):
            await service.confirm_password_reset(
                PasswordResetConfirmRequest(otp="123456", new_password="NewPassword@123!")
            )
