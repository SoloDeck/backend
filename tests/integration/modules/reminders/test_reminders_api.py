"""Integration tests for reminders CRUD and filters."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": f"u_{uuid.uuid4().hex[:8]}@example.com", "password": "Test@1234!", "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_deal_id(client: AsyncClient, headers: dict) -> str:
    c = await client.post("/api/v1/clients", json={"name": "Client", "status": "prospect"}, headers=headers)
    d = await client.post("/api/v1/deals", json={"client_id": c.json()["data"]["id"], "title": "Deal"}, headers=headers)
    return d.json()["data"]["id"]


def _reminder_payload(target_id: str, target_type: str = "deal", reminder_type: str = "follow_up") -> dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "reminder_type": reminder_type,
        "channel": "email",
        "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "message_preview": "Don't forget!",
    }


async def _create_reminder(client: AsyncClient, headers: dict, target_id: str, **kwargs) -> dict:
    resp = await client.post("/api/v1/reminders", json=_reminder_payload(target_id, **kwargs), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /reminders
# ---------------------------------------------------------------------------

class TestCreateReminder:
    async def test_creates_reminder_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.post("/api/v1/reminders", json=_reminder_payload(deal_id), headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["target_type"] == "deal"
        assert data["status"] == "pending"

    async def test_missing_required_fields_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post("/api/v1/reminders", json={"target_type": "deal"}, headers=headers)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/reminders", json=_reminder_payload(str(uuid.uuid4())))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reminders
# ---------------------------------------------------------------------------

class TestListReminders:
    async def test_returns_own_reminders(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        resp = await client.get("/api/v1/reminders", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    async def test_status_filter_pending(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        r = await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        # Cancel one
        await client.delete(f"/api/v1/reminders/{r['id']}", headers=headers)
        resp = await client.get("/api/v1/reminders?status=pending", headers=headers)
        data = resp.json()["data"]
        assert all(r["status"] == "pending" for r in data)

    async def test_status_filter_cancelled(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        r = await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        await client.delete(f"/api/v1/reminders/{r['id']}", headers=headers)
        resp = await client.get("/api/v1/reminders?status=cancelled", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "cancelled"

    async def test_target_type_filter_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id, target_type="deal")
        c = await client.post("/api/v1/clients", json={"name": "X", "status": "prospect"}, headers=headers)
        await _create_reminder(client, headers, c.json()["data"]["id"], target_type="client")
        resp = await client.get("/api/v1/reminders?target_type=deal", headers=headers)
        data = resp.json()["data"]
        assert all(r["target_type"] == "deal" for r in data)
        assert len(data) == 1

    async def test_target_type_filter_excludes_others(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id, target_type="deal")
        resp = await client.get("/api/v1/reminders?target_type=client", headers=headers)
        assert len(resp.json()["data"]) == 0

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        await _create_reminder(client, headers_a, deal_id)
        resp = await client.get("/api/v1/reminders", headers=headers_b)
        assert len(resp.json()["data"]) == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/reminders")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reminders/{id}
# ---------------------------------------------------------------------------

class TestGetReminder:
    async def test_returns_reminder(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == reminder["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/reminders/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/reminders/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /reminders/{id}
# ---------------------------------------------------------------------------

class TestUpdateReminder:
    async def test_updates_message_preview(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        payload = _reminder_payload(deal_id)
        payload["message_preview"] = "Updated message"
        resp = await client.patch(f"/api/v1/reminders/{reminder['id']}", json=payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["message_preview"] == "Updated message"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.patch(f"/api/v1/reminders/{uuid.uuid4()}", json=_reminder_payload(deal_id), headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.patch(f"/api/v1/reminders/{reminder['id']}", json=_reminder_payload(deal_id), headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        deal_id = str(uuid.uuid4())
        resp = await client.patch(f"/api/v1/reminders/{uuid.uuid4()}", json=_reminder_payload(deal_id))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /reminders/{id}
# ---------------------------------------------------------------------------

class TestCancelReminder:
    async def test_cancels_reminder(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        resp = await client.delete(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert resp.status_code == 200
        # Verify it's cancelled
        get_resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert get_resp.json()["data"]["status"] == "cancelled"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.delete(f"/api/v1/reminders/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.delete(f"/api/v1/reminders/{reminder['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/reminders/{uuid.uuid4()}")
        assert resp.status_code == 401
