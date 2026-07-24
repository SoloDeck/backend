"""Integration tests for /admin/* endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    AuditLogEntryModel,
    FeatureFlagModel,
    PlanModel,
    SubscriptionModel,
    SystemTemplateModel,
    UserModel,
)

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


async def _admin_headers_with_id(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[dict, str]:
    """Return (headers, user_id) for an admin user."""
    headers = await _admin_headers(client, db_session)
    me = await client.get("/api/v1/users/me", headers=headers)
    return headers, me.json()["data"]["id"]


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


async def _create_subscription(
    db_session: AsyncSession,
    user_id: str,
    plan_id: str,
    status: str = "active",
) -> None:
    """Insert a subscription directly into the DB for testing."""
    now = datetime.now(UTC)
    stmt = insert(SubscriptionModel).values(
        user_id=uuid.UUID(user_id),
        plan_id=uuid.UUID(plan_id),
        status=status,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    await db_session.execute(stmt)
    await db_session.flush()


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
        body = resp.json()["data"]
        assert body["total"] >= 3
        assert len(body["data"]) >= 3

    async def test_cross_tenant_visibility(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """Admin sees users registered by different parties."""
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)

        me = await client.get("/api/v1/users/me", headers=user_h)
        regular_id = me.json()["data"]["id"]

        resp = await client.get("/api/v1/admin/users", headers=headers)
        ids = [u["id"] for u in resp.json()["data"]["data"]]
        assert regular_id in ids

    async def test_response_has_expected_fields(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "data" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        user = body["data"][0]
        for field in ("id", "email", "full_name", "role", "status", "created_at"):
            assert field in user, f"Missing field: {field}"

    async def test_filter_by_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?status=active", headers=headers)
        assert resp.status_code == 200
        for u in resp.json()["data"]["data"]:
            assert u["status"] == "active"

    async def test_filter_by_role(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?role=freelancer", headers=headers)
        assert resp.status_code == 200
        for u in resp.json()["data"]["data"]:
            assert u["role"] == "freelancer"

    async def test_search_by_email(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        unique = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"srchemail_{unique}@example.com",
                "password": "Test@1234!",
                "full_name": "Email Search Target",
            },
        )
        resp = await client.get(f"/api/v1/admin/users?search=srchemail_{unique}", headers=headers)
        assert resp.status_code == 200
        results = resp.json()["data"]["data"]
        assert any(unique in u["email"] for u in results)

    async def test_search_by_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        unique = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"nmsrch_{unique}@example.com",
                "password": "Test@1234!",
                "full_name": f"NameSearch_{unique}",
            },
        )
        resp = await client.get(f"/api/v1/admin/users?search=NameSearch_{unique}", headers=headers)
        assert resp.status_code == 200
        results = resp.json()["data"]["data"]
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0]["full_name"] == f"NameSearch_{unique}"

    async def test_search_no_results(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/users?search=ZZZNOMATCH_xyzzy_abc123", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["total"] == 0
        assert body["data"] == []

    async def test_search_is_case_insensitive(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        unique = uuid.uuid4().hex[:8]
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"casetest_{unique}@example.com",
                "password": "Test@1234!",
                "full_name": f"CaseSensitive_{unique}",
            },
        )
        resp = await client.get(
            f"/api/v1/admin/users?search=casesensitive_{unique}", headers=headers
        )
        assert resp.status_code == 200
        results = resp.json()["data"]["data"]
        assert any(f"CaseSensitive_{unique}" == u["full_name"] for u in results)

    async def test_sort_by_email_asc(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?sort_by=email&sort_order=asc", headers=headers)
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()["data"]["data"]]
        assert emails == sorted(emails)

    async def test_filter_by_status_and_role_combined(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/users?status=active&role=freelancer", headers=headers
        )
        assert resp.status_code == 200
        for u in resp.json()["data"]["data"]:
            assert u["status"] == "active"
            assert u["role"] == "freelancer"

    async def test_invalid_role_returns_422(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?role=bogus", headers=headers)
        assert resp.status_code == 422

    async def test_invalid_status_returns_422(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?status=bogus", headers=headers)
        assert resp.status_code == 422

    async def test_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/users?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert len(body["data"]) <= 2

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

    async def test_includes_profile_and_preferences(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)

        me = await client.get("/api/v1/users/me", headers=user_h)
        user_id = me.json()["data"]["id"]

        resp = await client.get(f"/api/v1/admin/users/{user_id}", headers=headers)
        data = resp.json()["data"]
        assert "updated_at" in data
        assert "deleted_at" in data
        assert data["professional_profile"]["currency"] == "VND"
        assert data["preferences"]["locale"] == "vi"
        assert data["subscription"] is None

    async def test_includes_subscription_when_present(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        plan = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan["id"])

        resp = await client.get(f"/api/v1/admin/users/{user_id}", headers=headers)
        data = resp.json()["data"]
        assert data["subscription"]["plan_slug"] == plan["slug"]
        assert data["subscription"]["status"] == "active"

    async def test_list_includes_subscription(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        plan = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan["id"])

        resp = await client.get("/api/v1/admin/users?role=freelancer", headers=headers)
        users = {u["id"]: u for u in resp.json()["data"]["data"]}
        assert users[user_id]["subscription"]["plan_slug"] == plan["slug"]

    async def test_suspend_and_update_preserve_subscription(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        plan = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan["id"])

        resp = await client.post(f"/api/v1/admin/users/{user_id}/suspend", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["subscription"]["plan_slug"] == plan["slug"]

        resp = await client.post(f"/api/v1/admin/users/{user_id}/reinstate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["subscription"]["plan_slug"] == plan["slug"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}", json={"full_name": "X"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["subscription"]["plan_slug"] == plan["slug"]

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

    async def test_update_invalid_role_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"role": "superadmin"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_update_email(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"email": "renamed@example.com"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "renamed@example.com"

    async def test_update_phone(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"phone": "0933333333"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["phone"] == "0933333333"

    async def test_duplicate_email_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_a_h = await _user_headers(client)
        user_b_h = await _user_headers(client)
        email_a = (await client.get("/api/v1/users/me", headers=user_a_h)).json()["data"]["email"]
        user_b_id = (await client.get("/api/v1/users/me", headers=user_b_h)).json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/users/{user_b_id}",
            json={"email": email_a},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_duplicate_phone_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_a_h = await _user_headers(client)
        user_b_h = await _user_headers(client)
        user_a_id = (await client.get("/api/v1/users/me", headers=user_a_h)).json()["data"]["id"]
        user_b_id = (await client.get("/api/v1/users/me", headers=user_b_h)).json()["data"]["id"]

        await client.patch(
            f"/api/v1/admin/users/{user_a_id}", json={"phone": "0944444444"}, headers=headers
        )
        resp = await client.patch(
            f"/api/v1/admin/users/{user_b_id}", json={"phone": "0944444444"}, headers=headers
        )
        assert resp.status_code == 409

    async def test_reusing_own_email_is_not_a_conflict(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        me = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]

        resp = await client.patch(
            f"/api/v1/admin/users/{me['id']}",
            json={"email": me["email"], "full_name": "Renamed"},
            headers=headers,
        )
        assert resp.status_code == 200

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
# POST /admin/users/{user_id}/suspend
# ---------------------------------------------------------------------------


class TestAdminSuspendUser:
    async def test_suspend_regular_user(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.post(f"/api/v1/admin/users/{user_id}/suspend", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "suspended"

    async def test_cannot_suspend_last_active_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers, admin_id = await _admin_headers_with_id(client, db_session)
        resp = await client.post(f"/api/v1/admin/users/{admin_id}/suspend", headers=headers)
        assert resp.status_code == 409

    async def test_can_suspend_admin_when_another_admin_exists(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers, admin_id = await _admin_headers_with_id(client, db_session)
        # Create a second admin
        await _admin_headers(client, db_session)

        resp = await client.post(f"/api/v1/admin/users/{admin_id}/suspend", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "suspended"

    async def test_suspend_nonexistent_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/suspend", headers=headers)
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/suspend", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/suspend")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/users/{user_id}/reinstate
# ---------------------------------------------------------------------------


class TestAdminReinstateUser:
    async def test_reinstate_suspended_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        # Suspend first
        await client.post(f"/api/v1/admin/users/{user_id}/suspend", headers=headers)

        resp = await client.post(f"/api/v1/admin/users/{user_id}/reinstate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "active"

    async def test_reinstate_nonexistent_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/reinstate", headers=headers
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/reinstate", headers=headers
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /admin/users/{user_id}/sessions
# ---------------------------------------------------------------------------


class TestAdminRevokeUserSessions:
    async def test_revoke_returns_204(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        resp = await client.delete(f"/api/v1/admin/users/{user_id}/sessions", headers=headers)
        assert resp.status_code == 204

    async def test_revoke_user_with_no_tokens_returns_204(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.delete(
            f"/api/v1/admin/users/{uuid.uuid4()}/sessions", headers=headers
        )
        assert resp.status_code == 204

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.delete(
            f"/api/v1/admin/users/{uuid.uuid4()}/sessions", headers=headers
        )
        assert resp.status_code == 403


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
# GET /admin/plans/{plan_id}
# ---------------------------------------------------------------------------


class TestAdminGetPlan:
    async def test_returns_plan_by_id(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        created = (
            await client.post(
                "/api/v1/admin/plans",
                json=_plan_payload(name="Fetchable Plan", slug="fetchable-plan"),
                headers=headers,
            )
        ).json()["data"]

        resp = await client.get(f"/api/v1/admin/plans/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["slug"] == "fetchable-plan"

    async def test_nonexistent_plan_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(f"/api/v1/admin/plans/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get(f"/api/v1/admin/plans/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/admin/plans/{uuid.uuid4()}")
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

    async def test_duplicate_slug_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        await client.post(
            "/api/v1/admin/plans",
            json=_plan_payload(name="Original", slug="dup-slug"),
            headers=headers,
        )
        resp = await client.post(
            "/api/v1/admin/plans",
            json=_plan_payload(name="Different Name", slug="dup-slug"),
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_new_plan_is_always_active(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post(
            "/api/v1/admin/plans",
            json=_plan_payload(is_active=False),
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["is_active"] is True


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

    async def test_partial_update_only_changes_provided_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        created = (
            await client.post(
                "/api/v1/admin/plans",
                json=_plan_payload(name="Stable Name", slug="stable-slug", price_monthly="9.99"),
                headers=headers,
            )
        ).json()["data"]

        resp = await client.patch(
            f"/api/v1/admin/plans/{created['id']}",
            json={"price_monthly": 199000, "currency": "VND"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Stable Name"
        assert data["slug"] == "stable-slug"
        assert data["price_monthly"] == "199000.00"
        assert data["currency"] == "VND"

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

    async def test_duplicate_slug_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        await client.post(
            "/api/v1/admin/plans",
            json=_plan_payload(name="Plan A", slug="plan-a-slug"),
            headers=headers,
        )
        plan_b = (
            await client.post(
                "/api/v1/admin/plans",
                json=_plan_payload(name="Plan B", slug="plan-b-slug"),
                headers=headers,
            )
        ).json()["data"]

        resp = await client.patch(
            f"/api/v1/admin/plans/{plan_b['id']}",
            json={"slug": "plan-a-slug"},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_reusing_own_slug_is_not_a_conflict(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        created = (
            await client.post(
                "/api/v1/admin/plans",
                json=_plan_payload(name="Self Plan", slug="self-plan-slug"),
                headers=headers,
            )
        ).json()["data"]

        resp = await client.patch(
            f"/api/v1/admin/plans/{created['id']}",
            json={"slug": "self-plan-slug", "price_monthly": 15.0},
            headers=headers,
        )
        assert resp.status_code == 200

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


# ---------------------------------------------------------------------------
# GET /admin/subscriptions
# ---------------------------------------------------------------------------


class TestAdminListSubscriptions:
    async def test_returns_paginated_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/subscriptions", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "data" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body

    async def test_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/subscriptions?status=active", headers=headers
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]["data"]:
            assert item["status"] == "active"

    async def test_invalid_status_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/subscriptions?status=bogus", headers=headers
        )
        assert resp.status_code == 422

    async def test_subscription_has_plan_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Create a plan + subscription
        headers = await _admin_headers(client, db_session)
        plan_resp = await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        plan_id = plan_resp.json()["data"]["id"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan_id)

        resp = await client.get(
            f"/api/v1/admin/subscriptions?plan_slug={plan_resp.json()['data']['slug']}",
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["data"]
        assert len(items) >= 1
        assert "plan_name" in items[0]
        assert "plan_slug" in items[0]

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/subscriptions", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/subscriptions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/subscriptions/{subscription_id}/override
# ---------------------------------------------------------------------------


class TestAdminOverrideSubscription:
    async def test_override_plan(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)

        plan1 = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]
        plan2 = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan1["id"])

        # Get the subscription id
        subs_resp = await client.get(
            f"/api/v1/admin/subscriptions?plan_slug={plan1['slug']}", headers=headers
        )
        sub_id = subs_resp.json()["data"]["data"][0]["id"]

        resp = await client.patch(
            f"/api/v1/admin/subscriptions/{sub_id}/override",
            json={"plan_id": plan2["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["plan_id"] == plan2["id"]

    async def test_override_with_past_expiry_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)

        plan = (
            await client.post("/api/v1/admin/plans", json=_plan_payload(), headers=headers)
        ).json()["data"]

        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]
        await _create_subscription(db_session, user_id, plan["id"])

        subs_resp = await client.get(
            f"/api/v1/admin/subscriptions?plan_slug={plan['slug']}", headers=headers
        )
        sub_id = subs_resp.json()["data"]["data"][0]["id"]

        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        resp = await client.patch(
            f"/api/v1/admin/subscriptions/{sub_id}/override",
            json={"override_expires_at": past},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_override_nonexistent_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/subscriptions/{uuid.uuid4()}/override",
            json={"plan_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.patch(
            f"/api/v1/admin/subscriptions/{uuid.uuid4()}/override",
            json={},
            headers=headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/ai-costs
# ---------------------------------------------------------------------------


class TestAdminAiCosts:
    async def test_returns_paginated_response_with_totals(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/ai-costs", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "data" in body
        assert "total" in body
        assert "totals" in body
        assert "input_tokens" in body["totals"]
        assert "output_tokens" in body["totals"]
        assert "estimated_cost_usd" in body["totals"]

    async def test_invalid_ai_module_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/ai-costs?ai_module=bogus", headers=headers)
        assert resp.status_code == 422

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/ai-costs", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/ai-costs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/audit-logs
# ---------------------------------------------------------------------------


class TestAdminAuditLogs:
    async def test_returns_paginated_list(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "data" in body
        assert "total" in body

    async def test_suspend_creates_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        await client.post(f"/api/v1/admin/users/{user_id}/suspend", headers=headers)

        resp = await client.get(
            "/api/v1/admin/audit-logs?event_type=user.suspended", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    async def test_update_user_creates_audit_log(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        user_h = await _user_headers(client)
        user_id = (await client.get("/api/v1/users/me", headers=user_h)).json()["data"]["id"]

        await client.patch(
            f"/api/v1/admin/users/{user_id}",
            json={"full_name": "Audited Name"},
            headers=headers,
        )

        resp = await client.get(
            "/api/v1/admin/audit-logs?event_type=user.updated", headers=headers
        )
        assert resp.status_code == 200
        logs = resp.json()["data"]["data"]
        assert any("full_name=Audited Name" in e["description"] for e in logs)

    async def test_filter_by_event_type(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/audit-logs?event_type=user.suspended", headers=headers
        )
        assert resp.status_code == 200
        for entry in resp.json()["data"]["data"]:
            assert entry["event_type"] == "user.suspended"

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/audit-logs", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/audit-logs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /admin/templates
# ---------------------------------------------------------------------------


class TestAdminListTemplates:
    async def test_returns_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/templates", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_invalid_template_type_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get(
            "/api/v1/admin/templates?template_type=bogus", headers=headers
        )
        assert resp.status_code == 422

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/templates", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/templates")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/templates
# ---------------------------------------------------------------------------


class TestAdminCreateTemplate:
    def _template_payload(self, **overrides) -> dict:
        return {
            "name": f"Template {uuid.uuid4().hex[:6]}",
            "template_type": "proposal",
            "content": {"blocks": []},
            "plan_tier_required": None,
            "is_active": False,
            **overrides,
        }

    async def test_create_template_returns_201(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post(
            "/api/v1/admin/templates",
            json=self._template_payload(),
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "id" in data
        assert data["version_number"] == 1

    async def test_template_fields_persisted(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.post(
            "/api/v1/admin/templates",
            json=self._template_payload(
                name="My Template",
                template_type="contract",
                is_active=True,
                plan_tier_required="pro",
            ),
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "My Template"
        assert data["template_type"] == "contract"
        assert data["is_active"] is True
        assert data["plan_tier_required"] == "pro"

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.post(
            "/api/v1/admin/templates",
            json=self._template_payload(),
            headers=headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /admin/templates/{template_id}
# ---------------------------------------------------------------------------


class TestAdminUpdateTemplate:
    async def test_update_name(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        create_resp = await client.post(
            "/api/v1/admin/templates",
            json={
                "name": "Original",
                "template_type": "proposal",
                "content": {"v": 1},
                "is_active": False,
            },
            headers=headers,
        )
        template_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            f"/api/v1/admin/templates/{template_id}",
            json={"name": "Renamed"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Renamed"

    async def test_update_content_increments_version(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        create_resp = await client.post(
            "/api/v1/admin/templates",
            json={
                "name": "Template V1",
                "template_type": "proposal",
                "content": {"v": 1},
                "is_active": False,
            },
            headers=headers,
        )
        template_id = create_resp.json()["data"]["id"]
        original_version = create_resp.json()["data"]["version_number"]

        resp = await client.patch(
            f"/api/v1/admin/templates/{template_id}",
            json={"content": {"v": 2}},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["version_number"] == original_version + 1

    async def test_nonexistent_template_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/templates/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.patch(
            f"/api/v1/admin/templates/{uuid.uuid4()}",
            json={"name": "Nope"},
            headers=headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/feature-flags
# ---------------------------------------------------------------------------


class TestAdminListFeatureFlags:
    async def test_returns_list(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/feature-flags", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/feature-flags", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/feature-flags")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /admin/feature-flags/{flag_name}
# ---------------------------------------------------------------------------


class TestAdminUpdateFeatureFlag:
    async def _create_flag(self, db_session: AsyncSession, flag_name: str) -> None:
        stmt = insert(FeatureFlagModel).values(
            flag_name=flag_name,
            is_enabled=False,
            rollout_percentage=0,
        )
        await db_session.execute(stmt)
        await db_session.flush()

    async def test_update_flag_enabled(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        flag_name = f"test_flag_{uuid.uuid4().hex[:6]}"
        await self._create_flag(db_session, flag_name)

        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/feature-flags/{flag_name}",
            json={"is_enabled": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_enabled"] is True

    async def test_update_rollout_percentage(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        flag_name = f"rollout_flag_{uuid.uuid4().hex[:6]}"
        await self._create_flag(db_session, flag_name)

        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            f"/api/v1/admin/feature-flags/{flag_name}",
            json={"rollout_percentage": 50},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["rollout_percentage"] == 50

    async def test_nonexistent_flag_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.patch(
            "/api/v1/admin/feature-flags/nonexistent_flag_xyz",
            json={"is_enabled": True},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.patch(
            "/api/v1/admin/feature-flags/some_flag",
            json={"is_enabled": True},
            headers=headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/platform-metrics
# ---------------------------------------------------------------------------


class TestAdminPlatformMetrics:
    async def test_returns_metrics(self, client: AsyncClient, db_session: AsyncSession) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/platform-metrics", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        for field in (
            "total_users",
            "active_users",
            "suspended_users",
            "total_subscriptions",
            "active_subscriptions",
            "total_plans",
            "active_plans",
            "total_deals",
            "total_clients",
            "ai_cost_last_30_days",
        ):
            assert field in data, f"Missing metric: {field}"

    async def test_metrics_are_non_negative(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        resp = await client.get("/api/v1/admin/platform-metrics", headers=headers)
        data = resp.json()["data"]
        for field in ("total_users", "active_users", "suspended_users"):
            assert data[field] >= 0

    async def test_total_users_reflects_registrations(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await _admin_headers(client, db_session)
        before = (await client.get("/api/v1/admin/platform-metrics", headers=headers)).json()[
            "data"
        ]["total_users"]

        await _user_headers(client)

        after = (await client.get("/api/v1/admin/platform-metrics", headers=headers)).json()[
            "data"
        ]["total_users"]
        assert after == before + 1

    async def test_non_admin_returns_403(self, client: AsyncClient) -> None:
        headers = await _user_headers(client)
        resp = await client.get("/api/v1/admin/platform-metrics", headers=headers)
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/admin/platform-metrics")
        assert resp.status_code == 401
