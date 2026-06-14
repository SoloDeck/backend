"""Integration coverage for the public (unauthenticated) deal intake route.

POST /api/v1/intake/{share_token} — no auth. Verifies the happy path, bad-token
404, validation 422, and that the captured lead surfaces in the owner's GET /deals.
Uses real PostgreSQL (rolled back per test).
"""

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _owner_intake_token(client: AsyncClient) -> tuple[dict, str]:
    """Register an owner and return (auth_headers, intake_share_token)."""
    headers = await _auth_headers(client)
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200, me.text
    token = me.json()["data"]["intake_share_token"]
    assert token, "registration must mint an intake_share_token"
    return headers, token


async def test_public_intake_creates_lead_and_appears_in_owner_deals(client: AsyncClient) -> None:
    headers, token = await _owner_intake_token(client)

    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={
            "name": "Khách Hàng Mới",
            "email": "lead@example.com",
            "phone": "0900000000",
            "inquiry_text": "Cần thiết kế website bán hàng.",
            "estimated_budget": "20,000,000 VND",
            "desired_timeline": "1 tháng",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert "id" in body and "submitted_at" in body

    # The captured lead appears as a new_lead deal in the owner's pipeline.
    deals = await client.get("/api/v1/deals", headers=headers)
    assert deals.status_code == 200
    items = deals.json()["data"]
    assert any(d["stage"] == "new_lead" and "Khách Hàng Mới" in d["title"] for d in items)


async def test_public_intake_unknown_token_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/intake/this-token-does-not-exist",
        json={"name": "Nobody", "inquiry_text": "Hello"},
    )
    assert resp.status_code == 404


async def test_public_intake_empty_body_returns_422(client: AsyncClient) -> None:
    _, token = await _owner_intake_token(client)
    resp = await client.post(f"/api/v1/intake/{token}", json={})
    assert resp.status_code == 422


async def test_public_intake_oversized_inquiry_returns_422(client: AsyncClient) -> None:
    _, token = await _owner_intake_token(client)
    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={"name": "Lead", "inquiry_text": "x" * 5001},
    )
    assert resp.status_code == 422
