"""Integration tests for users /me endpoints."""

import uuid

from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register(client: AsyncClient, full_name: str = "Test User") -> tuple[dict, str]:
    email = f"u_{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Test@1234!", "full_name": full_name},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}, email


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


class TestGetMe:
    async def test_returns_own_profile(self, client: AsyncClient) -> None:
        headers, email = await _register(client, "Alice")
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["email"] == email
        assert data["full_name"] == "Alice"

    async def test_has_intake_share_token(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.json()["data"]["intake_share_token"] is not None

    async def test_includes_profile_and_preferences(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.get("/api/v1/users/me", headers=headers)
        data = resp.json()["data"]
        assert "updated_at" in data
        assert "bio" in data
        assert data["professional_profile"]["currency"] == "VND"
        assert data["preferences"]["locale"] == "vi"
        assert data["preferences"]["theme"] == "light"

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /users/me
# ---------------------------------------------------------------------------


class TestUpdateMe:
    async def test_updates_full_name(self, client: AsyncClient) -> None:
        headers, _ = await _register(client, "Old Name")
        resp = await client.patch(
            "/api/v1/users/me", json={"full_name": "New Name"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["full_name"] == "New Name"

    async def test_updates_phone(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch("/api/v1/users/me", json={"phone": "0901234567"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["phone"] == "0901234567"

    async def test_updates_avatar_url(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        new_avatar = "https://cdn.example.com/avatar.jpg"
        resp = await client.patch(
            "/api/v1/users/me", json={"avatar_url": new_avatar}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"] == new_avatar

    async def test_partial_update_leaves_name_unchanged(self, client: AsyncClient) -> None:
        headers, _ = await _register(client, "Keep Me")
        await client.patch("/api/v1/users/me", json={"phone": "09x"}, headers=headers)
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.json()["data"]["full_name"] == "Keep Me"

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/users/me", json={"full_name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /users/me
# ---------------------------------------------------------------------------


class TestDeleteMe:
    async def test_soft_deletes_account(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.delete("/api/v1/users/me", headers=headers)
        assert resp.status_code == 200

    async def test_deleted_user_cannot_fetch_profile(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        await client.delete("/api/v1/users/me", headers=headers)
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/v1/users/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /users/me/change-password
# ---------------------------------------------------------------------------


class TestChangePassword:
    async def test_correct_password_succeeds(self, client: AsyncClient) -> None:
        headers, email = await _register(client)
        resp = await client.post(
            "/api/v1/users/me/change-password",
            json={"current_password": "Test@1234!", "new_password": "NewPass@5678!"},
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_wrong_current_password_returns_401(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.post(
            "/api/v1/users/me/change-password",
            json={"current_password": "WrongPass!", "new_password": "NewPass@5678!"},
            headers=headers,
        )
        assert resp.status_code == 401

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/users/me/change-password",
            json={"current_password": "x", "new_password": "y"},
        )
        assert resp.status_code == 401
