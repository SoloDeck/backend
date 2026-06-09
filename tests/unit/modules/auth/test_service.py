"""Unit tests for AuthService.

All DB calls are mocked via AsyncMock — no real database required.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.auth.application.service import AuthService
from src.modules.auth.schemas.request import LoginRequest, RegisterRequest
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
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
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
