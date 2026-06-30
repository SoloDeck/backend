"""Integration tests for /admin/* endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import UserModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _user_headers(client: AsyncClient) -> dict:
    """Register a regular (freelancer) user and return auth headers."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _admin_headers(client: AsyncClient, db_session: AsyncSession) -> dict:
    """Register a user, promote to admin in DB, re-login to get admin JWT."""
    email = f"admin_{uuid.uuid4().hex[:8]}@example.com"
    password = "Admin@1234!"

    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test Admin"},
    )
    assert reg.status_code == 201, reg.text

    await db_session.execute(
        update(UserModel).where(UserModel.email == email).values(role="admin")
    )
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _plan_payload(**overrides: object) -> dict:
    return {
        "name": f"Plan {uuid.uuid4().hex[:6]}",
        "slug": f"plan-{uuid.uuid4().hex[:6]}",
        "price_monthly": "9.99",
        "currency": "USD",
        "can_use_ai": False,
        "can_export_pdf": False,
        "max_clients": None,
        "max_deals": None,
        "max_ai_generations_per_month": 0,
        "is_active": True,
        **overrides,
    }


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------


class TestAdminListUsers:
    async def test_admin_sees_all_users(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        await _user_headers(client)
        await _user_headers(client)

        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 3  # admin + 2 regular users

    async def test_cross_tenant_visibility(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Admin sees users registered by different parties."""
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)

        me = await client.get("/api/v1/users/me", headers=user_h)
        regular_id = me.json()["data"]["id"]

        resp = await client.get("/api/v1/admin/users", headers=headers)
        ids = [u["id"] for u in resp.json()["data"]]
        assert regular_id in ids

    async def test_response_has_expected_fields(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        user = resp.json()["data"][0]
        for field in ("id", "email", "full_name", "role", "status", "created_at"):
            assert field in user, f"Missing field: {field}"

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/users/{user_id}
# ---------------------------------------------------------------------------


class TestAdminGetUser:
    async def test_returns_correct_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)

        me = await client.get("/api/v1/users/me", headers=user_h)
        user_id = me.json()["data"]["id"]

        resp = await client.get(f"/api/v1/admin/users/{user_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == user_id

    async def test_nonexistent_user_returns_404(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}
# ---------------------------------------------------------------------------


class TestAdminUpdateUser:
    async def test_update_full_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"full_name": "Updated Name"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["full_name"] == "Updated Name"

    async def test_update_role_to_admin(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"role": "admin"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "admin"

    async def test_update_status_to_suspended(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"status": "suspended"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "suspended"

    async def test_update_nonexistent_returns_404(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}",
            json={"full_name": "Ghost"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}",
            json={"full_name": "Hijack"},
            headers=headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/admin/users/{uuid.uuid4()}",
            json={"full_name": "No Auth"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/plans
# ---------------------------------------------------------------------------


class TestAdminListPlans:
    async def test_returns_plans(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/plans", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_includes_created_plan(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        payload = _plan_payload(name="Visible Plan", slug="visible-plan")
        await client.post("/api/v1/admin/plans", json=payload, headers=headers)

        resp = await client.get("/api/v1/admin/plans", headers=headers)
        slugs = [p["slug"] for p in resp.json()["data"]]
        assert "visible-plan" in slugs

    async def test_response_has_expected_fields(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)

        resp = await client.get("/api/v1/admin/plans", headers=headers)
        plan = resp.json()["data"][0]
        for field in ("id", "name", "slug", "price_monthly", "can_use_ai", "is_active"):
            assert field in plan, f"Missing field: {field}"

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/plans", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/plans")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/plans
# ---------------------------------------------------------------------------


class TestAdminCreatePlan:
    async def test_create_plan_returns_201(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        assert resp.status_code == 201
        assert "id" in resp.json()["data"]

    async def test_fields_persisted(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        payload = _plan_payload(
            name="Pro Plan",
            slug="pro-plan",
            price_monthly="29.99",
            can_use_ai=True,
            can_export_pdf=True,
            max_clients=500,
            max_ai_generations_per_month=100,
        )
        resp = await client.post("/api/v1/admin/plans", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Pro Plan"
        assert data["slug"] == "pro-plan"
        assert data["can_use_ai"] is True
        assert data["max_clients"] == 500
        assert data["max_ai_generations_per_month"] == 100

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/admin/plans", json=_plan_payload())
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/plans/{plan_id}
# ---------------------------------------------------------------------------


class TestAdminUpdatePlan:
    async def test_update_plan_returns_200(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        plan_id = (await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)).json()["data"]["id"]

        updated = _plan_payload(name="Renamed Plan", slug="renamed-plan", price_monthly="49.99")
        resp = await client.patch(f"/api/v1/admin/plans/{plan_id}", json=updated, headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Renamed Plan"
        assert data["slug"] == "renamed-plan"

    async def test_deactivate_plan(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        plan_id = (await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/plans/{plan_id}",
            json=_plan_payload(is_active=False),
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    async def test_update_nonexistent_plan_returns_404(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/plans/{uuid.uuid4()}",
            json=_plan_payload(),
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.patch(f"/api/v1/admin/plans/{uuid.uuid4()}", json=_plan_payload(), headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(f"/api/v1/admin/plans/{uuid.uuid4()}", json=_plan_payload())
        assert resp.status_code == 401
