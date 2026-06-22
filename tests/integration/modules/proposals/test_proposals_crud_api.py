"""Integration tests for proposals CRUD and list filters."""

import uuid

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


async def _make_deal(client: AsyncClient, headers: dict, title: str = "Deal") -> str:
    c = await client.post("/api/v1/clients", json={"name": "Client", "status": "prospect"}, headers=headers)
    assert c.status_code == 201
    d = await client.post("/api/v1/deals", json={"client_id": c.json()["data"]["id"], "title": title}, headers=headers)
    assert d.status_code == 201
    return d.json()["data"]["id"]


async def _create_proposal(client: AsyncClient, headers: dict, deal_id: str) -> dict:
    resp = await client.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": {"summary": "Proposal text"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /proposals
# ---------------------------------------------------------------------------

class TestCreateProposal:
    async def test_creates_proposal_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        resp = await client.post(
            "/api/v1/proposals",
            json={"deal_id": deal_id, "content": {"body": "Hello"}},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["deal_id"] == deal_id
        assert data["status"] == "draft"

    async def test_unknown_deal_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/proposals",
            json={"deal_id": str(uuid.uuid4()), "content": {}},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_missing_deal_id_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post("/api/v1/proposals", json={"content": {}}, headers=headers)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/proposals", json={"deal_id": str(uuid.uuid4()), "content": {}})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /proposals
# ---------------------------------------------------------------------------

class TestListProposals:
    async def test_returns_own_proposals(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        await _create_proposal(client, headers, deal_id)
        await _create_proposal(client, headers, deal_id)
        resp = await client.get("/api/v1/proposals", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    async def test_filter_by_deal_id(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_a = await _make_deal(client, headers, "Deal A")
        deal_b = await _make_deal(client, headers, "Deal B")
        p_a = await _create_proposal(client, headers, deal_a)
        await _create_proposal(client, headers, deal_b)
        resp = await client.get(f"/api/v1/proposals?deal_id={deal_a}", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == p_a["id"]

    async def test_filter_by_deal_id_excludes_others(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_a = await _make_deal(client, headers, "A")
        deal_b = await _make_deal(client, headers, "B")
        await _create_proposal(client, headers, deal_a)
        await _create_proposal(client, headers, deal_b)
        resp = await client.get(f"/api/v1/proposals?deal_id={deal_b}", headers=headers)
        assert all(p["deal_id"] == deal_b for p in resp.json()["data"])

    async def test_filter_by_status(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        p = await _create_proposal(client, headers, deal_id)
        await client.patch(f"/api/v1/proposals/{p['id']}/status", json={"status": "sent"}, headers=headers)
        await _create_proposal(client, headers, deal_id)  # stays draft
        resp = await client.get("/api/v1/proposals?status=sent", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "sent"

    async def test_filter_status_excludes_other_statuses(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        await _create_proposal(client, headers, deal_id)
        resp = await client.get("/api/v1/proposals?status=sent", headers=headers)
        assert len(resp.json()["data"]) == 0

    async def test_pagination_page_size(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        for _ in range(5):
            await _create_proposal(client, headers, deal_id)
        resp = await client.get("/api/v1/proposals?page=1&page_size=3", headers=headers)
        assert len(resp.json()["data"]) == 3

    async def test_pagination_no_overlap(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        for _ in range(5):
            await _create_proposal(client, headers, deal_id)
        p1 = [p["id"] for p in (await client.get("/api/v1/proposals?page=1&page_size=3", headers=headers)).json()["data"]]
        p2 = [p["id"] for p in (await client.get("/api/v1/proposals?page=2&page_size=3", headers=headers)).json()["data"]]
        assert len(p2) == 2
        assert not set(p1) & set(p2)

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal(client, headers_a)
        await _create_proposal(client, headers_a, deal_id)
        resp = await client.get("/api/v1/proposals", headers=headers_b)
        assert len(resp.json()["data"]) == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/proposals")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /proposals/{id}
# ---------------------------------------------------------------------------

class TestGetProposal:
    async def test_returns_proposal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        proposal = await _create_proposal(client, headers, deal_id)
        resp = await client.get(f"/api/v1/proposals/{proposal['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == proposal["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/proposals/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal(client, headers_a)
        proposal = await _create_proposal(client, headers_a, deal_id)
        resp = await client.get(f"/api/v1/proposals/{proposal['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/proposals/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /proposals/{id}
# ---------------------------------------------------------------------------

class TestDeleteProposal:
    async def test_deletes_draft_returns_200(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        proposal = await _create_proposal(client, headers, deal_id)
        resp = await client.delete(f"/api/v1/proposals/{proposal['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_deleted_proposal_not_in_list(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)
        proposal = await _create_proposal(client, headers, deal_id)
        await client.delete(f"/api/v1/proposals/{proposal['id']}", headers=headers)
        ids = [p["id"] for p in (await client.get("/api/v1/proposals", headers=headers)).json()["data"]]
        assert proposal["id"] not in ids

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.delete(f"/api/v1/proposals/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal(client, headers_a)
        proposal = await _create_proposal(client, headers_a, deal_id)
        resp = await client.delete(f"/api/v1/proposals/{proposal['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/proposals/{uuid.uuid4()}")
        assert resp.status_code == 401
