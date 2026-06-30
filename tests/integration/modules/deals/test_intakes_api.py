"""Integration tests for GET /deals/intakes and GET /deals/intakes/{id}."""

import uuid
from unittest.mock import patch

from httpx import AsyncClient


async def _auth(client: AsyncClient) -> dict:
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


async def _intake_token(http: AsyncClient, headers: dict) -> str:
    me = await http.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200, me.text
    return me.json()["data"]["intake_share_token"]


async def _submit_intake(http: AsyncClient, token: str, name: str = "Test Lead") -> str:
    """Submit a public intake and return its id."""
    with patch("src.workers.ai_jobs.tasks.qualify_intake_async.delay"):
        resp = await http.post(
            f"/api/v1/intake/{token}",
            json={"name": name, "inquiry_text": "Need a website built.", "estimated_budget": "10M VND"},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


# ---------------------------------------------------------------------------
# GET /deals/intakes
# ---------------------------------------------------------------------------


class TestListIntakes:
    async def test_returns_own_intakes(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        await _submit_intake(client, token)

        resp = await client.get("/api/v1/deals/intakes", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1

    async def test_multiple_intakes_all_returned(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        await _submit_intake(client, token, "Lead A")
        await _submit_intake(client, token, "Lead B")
        await _submit_intake(client, token, "Lead C")

        resp = await client.get("/api/v1/deals/intakes", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 3

    async def test_response_has_expected_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        await _submit_intake(client, token)

        resp = await client.get("/api/v1/deals/intakes", headers=headers)
        item = resp.json()["data"][0]
        for field in ("id", "owner_user_id", "client_id", "inquiry_text", "submitted_at"):
            assert field in item, f"Missing field: {field}"

    async def test_estimated_budget_preserved(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        await _submit_intake(client, token)

        resp = await client.get("/api/v1/deals/intakes", headers=headers)
        item = resp.json()["data"][0]
        assert item["estimated_budget"] == "10M VND"

    async def test_pagination_page_size(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        for _ in range(5):
            await _submit_intake(client, token)

        resp = await client.get("/api/v1/deals/intakes?page=1&page_size=3", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 3

    async def test_pagination_no_overlap(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        for _ in range(5):
            await _submit_intake(client, token)

        p1 = {i["id"] for i in (await client.get("/api/v1/deals/intakes?page=1&page_size=3", headers=headers)).json()["data"]}
        p2 = {i["id"] for i in (await client.get("/api/v1/deals/intakes?page=2&page_size=3", headers=headers)).json()["data"]}
        assert len(p2) == 2
        assert not p1 & p2

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        """User B cannot see User A's intakes."""
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        token_a = await _intake_token(client, headers_a)
        await _submit_intake(client, token_a)

        resp = await client.get("/api/v1/deals/intakes", headers=headers_b)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/deals/intakes")
        assert resp.status_code == 401

    async def test_empty_list_when_no_intakes(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get("/api/v1/deals/intakes", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# GET /deals/intakes/{id}
# ---------------------------------------------------------------------------


class TestGetIntake:
    async def test_returns_correct_intake(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)
        intake_id = await _submit_intake(client, token)

        resp = await client.get(f"/api/v1/deals/intakes/{intake_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == intake_id

    async def test_inquiry_text_matches(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        token = await _intake_token(client, headers)

        with patch("src.workers.ai_jobs.tasks.qualify_intake_async.delay"):
            resp = await client.post(
                f"/api/v1/intake/{token}",
                json={"name": "Lead", "inquiry_text": "Build me a SaaS platform.", "estimated_budget": "50M VND"},
            )
        intake_id = resp.json()["data"]["id"]

        get_resp = await client.get(f"/api/v1/deals/intakes/{intake_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["inquiry_text"] == "Build me a SaaS platform."

    async def test_nonexistent_intake_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/deals/intakes/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_other_users_intake_returns_404(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        token_a = await _intake_token(client, headers_a)
        intake_id = await _submit_intake(client, token_a)

        resp = await client.get(f"/api/v1/deals/intakes/{intake_id}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/deals/intakes/{uuid.uuid4()}")
        assert resp.status_code == 401
