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
        db = _mock_db([None, _make_plan()])
        service = AuthService(db=db)
        result = await service.register(
            RegisterRequest(email="new@example.com", password="Test@1234!", full_name="New User")
        )
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "Bearer"

    async def test_creates_user_and_subscription_when_free_plan_exists(self) -> None:
        free_plan = _make_plan()
        db = _mock_db([None, free_plan])
        service = AuthService(db=db)
        await service.register(
            RegisterRequest(email="new@example.com", password="Test@1234!", full_name="New User")
        )
        assert db.add.call_count == 2

    async def test_creates_only_user_when_no_free_plan(self) -> None:
        db = _mock_db([None, None])
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
        db = _mock_db([user])
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
