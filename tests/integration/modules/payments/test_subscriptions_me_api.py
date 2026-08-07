"""Integration tests for POST /subscriptions/me/{upgrade,downgrade} and GET /me/usage."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.seeders.plans import PlansSeeder
from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _plan_by_slug(client: AsyncClient, headers: dict, slug: str) -> dict:
    resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    assert resp.status_code == 200
    return next(p for p in resp.json()["data"] if p["slug"] == slug)


class TestGetUsage:
    async def test_returns_zero_usage_for_new_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)

        resp = await client.get("/api/v1/subscriptions/me/usage", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["ai_generations_used"] == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/subscriptions/me/usage")
        assert resp.status_code == 401


class TestUpgradeSubscription:
    async def test_upgrade_to_pro_switches_plan_immediately(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)
        pro = await _plan_by_slug(client, headers, "pro")

        resp = await client.post(
            "/api/v1/subscriptions/me/upgrade",
            json={"plan_id": pro["id"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["plan_slug"] == "pro"
        assert body["status"] == "active"
        assert body["cancel_at_period_end"] is False

    async def test_upgrade_to_cheaper_or_equal_plan_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)
        free = await _plan_by_slug(client, headers, "free")

        resp = await client.post(
            "/api/v1/subscriptions/me/upgrade",
            json={"plan_id": free["id"]},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_upgrade_to_nonexistent_plan_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)

        resp = await client.post(
            "/api/v1/subscriptions/me/upgrade",
            json={"plan_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/subscriptions/me/upgrade", json={"plan_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 401


class TestDowngradeSubscription:
    async def test_downgrade_schedules_lapse_at_period_end(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)
        pro = await _plan_by_slug(client, headers, "pro")
        free = await _plan_by_slug(client, headers, "free")

        await client.post(
            "/api/v1/subscriptions/me/upgrade", json={"plan_id": pro["id"]}, headers=headers
        )
        resp = await client.post(
            "/api/v1/subscriptions/me/downgrade",
            json={"plan_id": free["id"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["cancel_at_period_end"] is True
        # Access continues on the current (pro) plan until period end.
        assert body["plan_slug"] == "pro"

    async def test_downgrade_to_more_expensive_plan_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)
        pro = await _plan_by_slug(client, headers, "pro")

        resp = await client.post(
            "/api/v1/subscriptions/me/downgrade",
            json={"plan_id": pro["id"]},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_downgrade_twice_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await PlansSeeder(db_session).run()
        headers = await _auth_headers(client)
        free = await _plan_by_slug(client, headers, "free")

        await client.post(
            "/api/v1/subscriptions/me/downgrade", json={"plan_id": free["id"]}, headers=headers
        )
        resp = await client.post(
            "/api/v1/subscriptions/me/downgrade",
            json={"plan_id": free["id"]},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/subscriptions/me/downgrade", json={"plan_id": str(uuid.uuid4())}
        )
        assert resp.status_code == 401
