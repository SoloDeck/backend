"""Integration tests for the public (unauthenticated) proposal endpoints."""

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


async def _create_sent_proposal(http: AsyncClient, headers: dict, deal_id: str) -> tuple[str, str]:
    """Returns (proposal_id, share_token)."""
    resp = await http.post(
        "/api/v1/proposals",
        json={
            "deal_id": deal_id,
            "content": {
                "body": "proposal body",
                "pricing": {"total": 5_000_000, "currency": "VND"},
                # Cổng gửi của main đòi hạng mục chi phí (mục 7), không chỉ một con số tổng:
                # mỗi hạng mục là một đợt thu tiền. Tổng các dòng phải KHỚP giá chào.
                "pricing_items": [
                    {"label": "Thiết kế", "amount": 2_000_000},
                    {"label": "Phát triển", "amount": 3_000_000},
                ],
            },
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["data"]["id"]

    sent = await http.post(f"/api/v1/proposals/{pid}/send", headers=headers)
    assert sent.status_code == 200, sent.text
    return pid, sent.json()["data"]["share_token"]


class TestSendGeneratesShareToken:
    async def test_send_sets_share_token_and_expiry(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid, share_token = await _create_sent_proposal(client, headers, did)

        assert share_token is not None
        assert len(share_token) > 20


class TestGetPublicProposal:
    async def test_returns_read_only_view(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        _, share_token = await _create_sent_proposal(client, headers, did)

        resp = await client.get(f"/api/v1/proposals/public/{share_token}")
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["status"] == "sent"
        assert "content" in body
        assert "id" not in body
        assert "owner_user_id" not in body

    async def test_bad_token_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/proposals/public/not-a-real-token")
        assert resp.status_code == 404, resp.text


class TestRespondToProposal:
    async def test_accept_transitions_status(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid, share_token = await _create_sent_proposal(client, headers, did)

        resp = await client.post(
            f"/api/v1/proposals/public/{share_token}/respond",
            json={"decision": "accepted", "note": "Looks great!"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["status"] == "accepted"
        assert body["responded_at"] is not None

    async def test_reject_transitions_status(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid, share_token = await _create_sent_proposal(client, headers, did)

        resp = await client.post(
            f"/api/v1/proposals/public/{share_token}/respond",
            json={"decision": "rejected"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "rejected"

    async def test_responding_twice_returns_409(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid, share_token = await _create_sent_proposal(client, headers, did)

        await client.post(
            f"/api/v1/proposals/public/{share_token}/respond",
            json={"decision": "accepted"},
        )
        resp = await client.post(
            f"/api/v1/proposals/public/{share_token}/respond",
            json={"decision": "rejected"},
        )
        assert resp.status_code == 409, resp.text

    async def test_bad_token_returns_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/proposals/public/not-a-real-token/respond",
            json={"decision": "accepted"},
        )
        assert resp.status_code == 404, resp.text

    async def test_invalid_decision_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        cid = await _create_client(client, headers)
        did = await _create_deal(client, headers, cid)
        pid, share_token = await _create_sent_proposal(client, headers, did)

        resp = await client.post(
            f"/api/v1/proposals/public/{share_token}/respond",
            json={"decision": "maybe"},
        )
        assert resp.status_code == 422, resp.text
