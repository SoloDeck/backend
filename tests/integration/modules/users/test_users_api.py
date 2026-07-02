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

    async def test_updates_bio(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me", json={"bio": "Full-stack freelancer."}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["bio"] == "Full-stack freelancer."

    async def test_partial_update_leaves_name_unchanged(self, client: AsyncClient) -> None:
        headers, _ = await _register(client, "Keep Me")
        await client.patch("/api/v1/users/me", json={"phone": "09x"}, headers=headers)
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.json()["data"]["full_name"] == "Keep Me"

    async def test_email_field_is_ignored(self, client: AsyncClient) -> None:
        headers, email = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me", json={"email": "someone-else@example.com"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == email

    async def test_duplicate_phone_returns_409(self, client: AsyncClient) -> None:
        headers_a, _ = await _register(client)
        headers_b, _ = await _register(client)
        await client.patch("/api/v1/users/me", json={"phone": "0911111111"}, headers=headers_a)
        resp = await client.patch(
            "/api/v1/users/me", json={"phone": "0911111111"}, headers=headers_b
        )
        assert resp.status_code == 409

    async def test_reusing_own_phone_is_not_a_conflict(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        await client.patch("/api/v1/users/me", json={"phone": "0922222222"}, headers=headers)
        resp = await client.patch(
            "/api/v1/users/me",
            json={"phone": "0922222222", "full_name": "Renamed"},
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/users/me", json={"full_name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /users/me/professional-profile
# ---------------------------------------------------------------------------


class TestUpdateProfessionalProfile:
    async def test_updates_profile_fields(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me/professional-profile",
            json={
                "skills": ["Administration", "Programming", "HR"],
                "specialization": "Java",
                "default_hourly_rate": 200000,
                "currency": "VND",
                "portfolio_url": "https://example.com/",
                "business_name": "SoloDesk Freelancer",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        profile = resp.json()["data"]["professional_profile"]
        assert profile["skills"] == ["Administration", "Programming", "HR"]
        assert profile["specialization"] == "Java"
        assert profile["default_hourly_rate"] == "200000.00"
        assert profile["portfolio_url"] == "https://example.com/"
        assert profile["business_name"] == "SoloDesk Freelancer"

    async def test_partial_update_leaves_other_fields(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        await client.patch(
            "/api/v1/users/me/professional-profile",
            json={"specialization": "Java"},
            headers=headers,
        )
        resp = await client.patch(
            "/api/v1/users/me/professional-profile",
            json={"business_name": "Solo Studio"},
            headers=headers,
        )
        profile = resp.json()["data"]["professional_profile"]
        assert profile["specialization"] == "Java"
        assert profile["business_name"] == "Solo Studio"

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/users/me/professional-profile", json={"specialization": "Java"}
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /users/me/preferences
# ---------------------------------------------------------------------------


class TestUpdatePreferences:
    async def test_updates_preference_fields(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me/preferences",
            json={
                "locale": "en",
                "timezone": "UTC",
                "notification_channel": "both",
                "theme": "dark",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        prefs = resp.json()["data"]["preferences"]
        assert prefs == {
            "locale": "en",
            "timezone": "UTC",
            "notification_channel": "both",
            "theme": "dark",
        }

    async def test_partial_update_leaves_other_fields(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        await client.patch(
            "/api/v1/users/me/preferences", json={"theme": "dark"}, headers=headers
        )
        resp = await client.patch(
            "/api/v1/users/me/preferences", json={"locale": "en"}, headers=headers
        )
        prefs = resp.json()["data"]["preferences"]
        assert prefs["theme"] == "dark"
        assert prefs["locale"] == "en"

    async def test_invalid_theme_returns_422(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me/preferences", json={"theme": "neon"}, headers=headers
        )
        assert resp.status_code == 422

    async def test_invalid_notification_channel_returns_422(self, client: AsyncClient) -> None:
        headers, _ = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me/preferences",
            json={"notification_channel": "sms"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch("/api/v1/users/me/preferences", json={"theme": "dark"})
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
