"""Integration tests for auth API endpoints.

Uses real PostgreSQL (rolled back per test via db_session fixture).
Asserts the standard response envelope shape on every response.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_payload(**overrides: object) -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
        **overrides,
    }


async def _register(client: AsyncClient, **overrides: object) -> dict:
    resp = await client.post("/api/v1/auth/register", json=_register_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestRegisterEndpoint:
    async def test_success_returns_201_with_envelope(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/auth/register", json=_register_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == 201
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]
        assert body["data"]["token_type"] == "Bearer"

    async def test_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        payload = _register_payload()
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "CONFLICT"

    async def test_missing_password_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "x@x.com", "full_name": "No Pass"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_FAILED"
        fields = [d["field"] for d in body["error"]["details"]]
        assert "password" in fields

    async def test_invalid_email_format_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "notanemail", "password": "Test@1234!", "full_name": "Bad Email"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLoginEndpoint:
    async def test_success_returns_200_with_envelope(self, client: AsyncClient) -> None:
        payload = _register_payload()
        await _register(client, **payload)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == 200
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]

    async def test_wrong_password_returns_401(self, client: AsyncClient) -> None:
        payload = _register_payload()
        await _register(client, **payload)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "UNAUTHORIZED"

    async def test_nonexistent_user_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "Test@1234!"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    async def test_missing_field_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@x.com"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_FAILED"
        fields = [d["field"] for d in body["error"]["details"]]
        assert "password" in fields

    async def test_suspended_account_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from src.infrastructure.database.models import UserModel

        payload = _register_payload()
        await _register(client, **payload)

        user = await db_session.scalar(select(UserModel).where(UserModel.email == payload["email"]))
        assert user is not None
        user.status = "suspended"
        await db_session.flush()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogoutEndpoint:
    async def test_blacklisted_access_token_rejected_on_next_request(
        self, client: AsyncClient
    ) -> None:
        tokens = await _register(client)
        access_token = tokens["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        me_resp = await client.get("/api/v1/users/me", headers=headers)
        assert me_resp.status_code == 200

        logout_resp = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_resp.status_code == 200

        me_resp_after = await client.get("/api/v1/users/me", headers=headers)
        assert me_resp_after.status_code == 401
        assert me_resp_after.json()["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefreshEndpoint:
    async def test_success_returns_200_with_new_tokens(self, client: AsyncClient) -> None:
        tokens = await _register(client)
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["data"]["refresh_token"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]

    async def test_replaying_a_consumed_refresh_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        tokens = await _register(client)
        refresh_token = tokens["data"]["refresh_token"]

        first = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert first.status_code == 200

        replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "UNAUTHORIZED"

    async def test_new_refresh_token_from_rotation_still_works_once(
        self, client: AsyncClient
    ) -> None:
        tokens = await _register(client)
        first = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["data"]["refresh_token"]},
        )
        rotated_refresh_token = first.json()["data"]["refresh_token"]

        second = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated_refresh_token}
        )
        assert second.status_code == 200

    async def test_blacklisted_refresh_token_returns_401(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from jose import jwt
        from sqlalchemy import select

        from src.config.settings import settings
        from src.infrastructure.database.models import TokenBlacklistModel, UserModel

        tokens = await _register(client)
        refresh_token = tokens["data"]["refresh_token"]
        claims = jwt.decode(
            refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )

        user = await db_session.scalar(
            select(UserModel).where(UserModel.id == uuid.UUID(claims["sub"]))
        )
        assert user is not None
        db_session.add(
            TokenBlacklistModel(
                jti=claims["jti"],
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await db_session.flush()

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"
