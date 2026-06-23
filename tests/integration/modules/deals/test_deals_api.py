"""Integration tests for deals CRUD and list filters."""

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


async def _create_client(client: AsyncClient, headers: dict, name: str = "Acme") -> str:
    resp = await client.post("/api/v1/clients", json={"name": name, "status": "prospect"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(
    client: AsyncClient, headers: dict,
    title: str = "My Deal", stage: str = "new_lead", client_id: str | None = None,
) -> dict:
    if client_id is None:
        client_id = await _create_client(client, headers)
    resp = await client.post(
        "/api/v1/deals",
        json={"client_id": client_id, "title": title, "stage": stage},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /deals
# ---------------------------------------------------------------------------

class TestCreateDeal:
    async def test_creates_deal_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        client_id = await _create_client(client, headers)
        resp = await client.post("/api/v1/deals", json={"client_id": client_id, "title": "Deal A"}, headers=headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Deal A"
        assert data["stage"] == "new_lead"

    async def test_unknown_client_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post("/api/v1/deals", json={"client_id": str(uuid.uuid4()), "title": "X"}, headers=headers)
        assert resp.status_code == 404

    async def test_missing_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        client_id = await _create_client(client, headers)
        resp = await client.post("/api/v1/deals", json={"client_id": client_id}, headers=headers)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/deals", json={"client_id": str(uuid.uuid4()), "title": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /deals
# ---------------------------------------------------------------------------

class TestListDeals:
    async def test_returns_own_deals(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "Deal 1")
        await _create_deal(client, headers, "Deal 2")
        resp = await client.get("/api/v1/deals", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    async def test_title_filter_partial_match(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "Website Redesign")
        await _create_deal(client, headers, "Logo Design")
        resp = await client.get("/api/v1/deals?title=website", headers=headers)
        titles = [d["title"] for d in resp.json()["data"]]
        assert "Website Redesign" in titles
        assert "Logo Design" not in titles

    async def test_title_filter_case_insensitive(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "Mobile App")
        resp = await client.get("/api/v1/deals?title=MOBILE", headers=headers)
        assert len(resp.json()["data"]) == 1

    async def test_stage_filter(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "New", stage="new_lead")
        await _create_deal(client, headers, "Qualified", stage="qualified")
        resp = await client.get("/api/v1/deals?stage=qualified", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["stage"] == "qualified"

    async def test_stage_filter_excludes_other_stages(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "Lead", stage="new_lead")
        await _create_deal(client, headers, "Prop", stage="proposal_sent")
        resp = await client.get("/api/v1/deals?stage=new_lead", headers=headers)
        stages = [d["stage"] for d in resp.json()["data"]]
        assert all(s == "new_lead" for s in stages)

    async def test_title_and_stage_combined(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "Alpha Lead", stage="new_lead")
        await _create_deal(client, headers, "Alpha Qualified", stage="qualified")
        resp = await client.get("/api/v1/deals?title=alpha&stage=qualified", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["title"] == "Alpha Qualified"

    async def test_pagination_page_size(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        c_id = await _create_client(client, headers)
        for i in range(5):
            await _create_deal(client, headers, f"Deal {i}", client_id=c_id)
        resp = await client.get("/api/v1/deals?page=1&page_size=3", headers=headers)
        assert len(resp.json()["data"]) == 3

    async def test_pagination_second_page(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        c_id = await _create_client(client, headers)
        for i in range(5):
            await _create_deal(client, headers, f"Paged {i}", client_id=c_id)
        p1 = [d["id"] for d in (await client.get("/api/v1/deals?page=1&page_size=3", headers=headers)).json()["data"]]
        p2 = [d["id"] for d in (await client.get("/api/v1/deals?page=2&page_size=3", headers=headers)).json()["data"]]
        assert len(p2) == 2
        assert not set(p1) & set(p2)

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        await _create_deal(client, headers_a, "User A Deal")
        resp = await client.get("/api/v1/deals", headers=headers_b)
        assert len(resp.json()["data"]) == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/deals")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /deals/{id}
# ---------------------------------------------------------------------------

class TestGetDeal:
    async def test_returns_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Fetch Me")
        resp = await client.get(f"/api/v1/deals/{deal['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Fetch Me"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/deals/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal = await _create_deal(client, headers_a, "Private")
        resp = await client.get(f"/api/v1/deals/{deal['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/deals/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /deals/{id}
# ---------------------------------------------------------------------------

class TestUpdateDeal:
    async def test_updates_title(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Old Title")
        client_id = deal["client_id"]
        resp = await client.patch(
            f"/api/v1/deals/{deal['id']}",
            json={"client_id": client_id, "title": "New Title"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "New Title"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        client_id = await _create_client(client, headers)
        resp = await client.patch(
            f"/api/v1/deals/{uuid.uuid4()}",
            json={"client_id": client_id, "title": "X"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal = await _create_deal(client, headers_a, "Alice Deal")
        client_id = deal["client_id"]
        resp = await client.patch(
            f"/api/v1/deals/{deal['id']}",
            json={"client_id": client_id, "title": "Hijacked"},
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(f"/api/v1/deals/{uuid.uuid4()}", json={"client_id": str(uuid.uuid4()), "title": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /deals/{id}
# ---------------------------------------------------------------------------

class TestDeleteDeal:
    async def test_soft_deletes_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "To Delete")
        resp = await client.delete(f"/api/v1/deals/{deal['id']}", headers=headers)
        assert resp.status_code == 200

    async def test_deleted_deal_not_in_list(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Gone")
        await client.delete(f"/api/v1/deals/{deal['id']}", headers=headers)
        ids = [d["id"] for d in (await client.get("/api/v1/deals", headers=headers)).json()["data"]]
        assert deal["id"] not in ids

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.delete(f"/api/v1/deals/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal = await _create_deal(client, headers_a, "Owned by A")
        resp = await client.delete(f"/api/v1/deals/{deal['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/deals/{uuid.uuid4()}")
        assert resp.status_code == 401
