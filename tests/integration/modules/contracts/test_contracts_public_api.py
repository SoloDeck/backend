"""Integration tests for the public (unauthenticated) contract endpoints."""

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
        json={"name": "Acme Corp", "status": "prospect"},
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


async def _create_accepted_proposal(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={
            "deal_id": deal_id,
            "content": {
                "body": "proposal body",
                "pricing": {"total": 5_000_000, "currency": "VND"},
            },
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["data"]["id"]

    await http.patch(f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers)
    r = await http.patch(
        f"/api/v1/proposals/{pid}/status", json={"status": "accepted"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return pid


async def _create_sent_contract(
    http: AsyncClient, headers: dict, deal_id: str, proposal_id: str, client_id: str
) -> tuple[str, str]:
    """Returns (contract_id, share_token)."""
    resp = await http.post(
        "/api/v1/contracts",
        json={
            "deal_id": deal_id,
            "proposal_id": proposal_id,
            "client_id": client_id,
            "content": {"scope_of_work": "Build a website"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    contract_id = resp.json()["data"]["id"]

    sent = await http.post(f"/api/v1/contracts/{contract_id}/send", headers=headers)
    assert sent.status_code == 200, sent.text
    return contract_id, sent.json()["data"]["share_token"]


async def _setup_sent_contract(client: AsyncClient) -> tuple[dict, str, str, str]:
    """Returns (headers, deal_id, contract_id, share_token)."""
    headers = await _auth(client)
    cid = await _create_client(client, headers)
    did = await _create_deal(client, headers, cid)
    pid = await _create_accepted_proposal(client, headers, did)
    contract_id, share_token = await _create_sent_contract(client, headers, did, pid, cid)
    return headers, did, contract_id, share_token


class TestSendGeneratesShareToken:
    async def test_send_sets_share_token(self, client: AsyncClient) -> None:
        _, _, _, share_token = await _setup_sent_contract(client)
        assert share_token is not None
        assert len(share_token) > 20


class TestGetPublicContract:
    async def test_returns_read_only_view(self, client: AsyncClient) -> None:
        _, _, _, share_token = await _setup_sent_contract(client)

        resp = await client.get(f"/api/v1/contracts/public/{share_token}")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["status"] == "pending_signatures"
        assert "content" in body
        assert "id" not in body
        assert "owner_user_id" not in body

    async def test_bad_token_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/contracts/public/not-a-real-token")
        assert resp.status_code == 404, resp.text


class TestSignContract:
    async def test_client_signs_first_stays_pending(self, client: AsyncClient) -> None:
        _, _, _, share_token = await _setup_sent_contract(client)

        resp = await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={"signer_name": "Jane Client"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["status"] == "pending_signatures"
        assert body["signed_by_client_at"] is not None
        assert body["signed_by_freelancer_at"] is None

    async def test_client_then_freelancer_activates_and_creates_project(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id, contract_id, share_token = await _setup_sent_contract(client)

        await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={"signer_name": "Jane Client"},
        )
        resp = await client.post(f"/api/v1/contracts/{contract_id}/sign", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "active"

        projects = await client.get(
            f"/api/v1/projects?deal_id={deal_id}", headers=headers
        )
        assert projects.json()["pagination"]["total"] == 1

    async def test_freelancer_then_client_activates_and_creates_project(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id, contract_id, share_token = await _setup_sent_contract(client)

        await client.post(f"/api/v1/contracts/{contract_id}/sign", headers=headers)
        resp = await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={"signer_name": "Bob Client"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "active"

        projects = await client.get(
            f"/api/v1/projects?deal_id={deal_id}", headers=headers
        )
        assert projects.json()["pagination"]["total"] == 1

    async def test_signing_already_active_contract_returns_409(
        self, client: AsyncClient
    ) -> None:
        headers, _, contract_id, share_token = await _setup_sent_contract(client)
        await client.post(f"/api/v1/contracts/{contract_id}/sign", headers=headers)
        await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={"signer_name": "Bob Client"},
        )

        resp = await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={"signer_name": "Second Attempt"},
        )
        assert resp.status_code == 409, resp.text

    async def test_bad_token_returns_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/contracts/public/not-a-real-token/sign",
            json={"signer_name": "Nobody"},
        )
        assert resp.status_code == 404, resp.text

    async def test_missing_signer_name_returns_422(self, client: AsyncClient) -> None:
        _, _, _, share_token = await _setup_sent_contract(client)

        resp = await client.post(
            f"/api/v1/contracts/public/{share_token}/sign",
            json={},
        )
        assert resp.status_code == 422, resp.text
