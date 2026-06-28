"""Integration tests for PATCH /proposals/:id/status."""

import uuid

from httpx import AsyncClient


def _reg(**overrides: object) -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
        **overrides,
    }


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/auth/register", json=_reg())
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_client(http: AsyncClient, headers: dict) -> str:
    resp = await http.post(
        "/api/v1/clients",
        json={"name": "Acme", "status": "prospect"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(http: AsyncClient, headers: dict, client_id: str) -> str:
    resp = await http.post(
        "/api/v1/deals",
        json={"title": "Test deal", "client_id": client_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_proposal(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": {"body": "proposal body"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


class TestTransitionProposalStatus:
    async def test_draft_to_sent_returns_200(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_proposal(client, headers, did)

        resp = await client.patch(
            f"/api/v1/proposals/{pid}/status",
            json={"status": "sent"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "sent"
        assert body["data"]["sent_at"] is not None

    async def test_sent_to_accepted_returns_200(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_proposal(client, headers, did)

        await client.patch(
            f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers
        )
        resp = await client.patch(
            f"/api/v1/proposals/{pid}/status",
            json={"status": "accepted"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "accepted"
        assert resp.json()["data"]["responded_at"] is not None

    async def test_invalid_transition_returns_409(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid = await _create_proposal(client, headers, did)

        resp = await client.patch(
            f"/api/v1/proposals/{pid}/status",
            json={"status": "accepted"},  # draft → accepted is not allowed
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            f"/api/v1/proposals/{uuid.uuid4()}/status",
            json={"status": "sent"},
            headers=headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            f"/api/v1/proposals/{uuid.uuid4()}/status",
            json={"status": "sent"},
        )
        assert resp.status_code == 401, resp.text

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        cid = await _create_client(client, headers_a)
        did = await _create_deal(client, headers_a, cid)
        pid = await _create_proposal(client, headers_a, did)

        resp = await client.patch(
            f"/api/v1/proposals/{pid}/status",
            json={"status": "sent"},
            headers=headers_b,
        )
        assert resp.status_code == 404, resp.text

    async def test_sending_supersedes_existing_sent(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)

        # Create and send first proposal
        pid1 = await _create_proposal(client, headers, did)
        await client.patch(
            f"/api/v1/proposals/{pid1}/status", json={"status": "sent"}, headers=headers
        )

        # Create and send second proposal on same deal — first should be superseded
        pid2 = await _create_proposal(client, headers, did)
        resp = await client.patch(
            f"/api/v1/proposals/{pid2}/status", json={"status": "sent"}, headers=headers
        )
        assert resp.status_code == 200, resp.text

        first = await client.get(f"/api/v1/proposals/{pid1}", headers=headers)
        assert first.json()["data"]["status"] == "superseded"
