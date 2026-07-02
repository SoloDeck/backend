"""Integration tests for POST /proposals/generate-from-deal/{deal_id}."""

import uuid

import pytest
from httpx import AsyncClient

from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from src.shared.exceptions.domain import EntitlementError

# ---------------------------------------------------------------------------
# Fake AI facades
# ---------------------------------------------------------------------------

_FAKE_CONTENT = {
    "project_overview": "Build a modern e-commerce platform.",
    "scope_of_work": ["Backend API", "Frontend UI", "Payment integration"],
    "deliverables": ["Deployed application", "Source code", "Documentation"],
    "timeline": "8 weeks",
    "pricing": "50,000,000 VND",
    "payment_terms": "50% upfront, 50% on delivery",
    "assumptions": "Client provides brand assets",
}


class _PermissiveAIFacade:
    """Always returns fake content regardless of entitlement."""

    async def generate_proposal(self, *, deal_data, client_data, user_profile, template, user_can_use_ai):
        return _FAKE_CONTENT


class _StrictAIFacade:
    """Mirrors real entitlement check — raises 402 when user_can_use_ai=False."""

    async def generate_proposal(self, *, deal_data, client_data, user_profile, template, user_can_use_ai):
        if not user_can_use_ai:
            raise EntitlementError(
                "Your plan does not include AI features. Upgrade to Pro.",
                entitlement="can_use_ai",
            )
        return _FAKE_CONTENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _make_deal(http: AsyncClient, headers: dict, title: str = "Website Redesign") -> str:
    c = await http.post(
        "/api/v1/clients",
        json={"name": "Acme Corp", "status": "prospect"},
        headers=headers,
    )
    assert c.status_code == 201, c.text
    d = await http.post(
        "/api/v1/deals",
        json={"client_id": c.json()["data"]["id"], "title": title},
        headers=headers,
    )
    assert d.status_code == 201, d.text
    return d.json()["data"]["id"]


# ---------------------------------------------------------------------------
# POST /proposals/generate-from-deal/{deal_id}
# ---------------------------------------------------------------------------


class TestGenerateFromDeal:
    @pytest.fixture(autouse=True)
    def _use_permissive_ai(self):
        """Inject permissive AI stub for all tests in this class (bypasses entitlement)."""
        app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
        yield
        app.dependency_overrides.pop(get_ai_facade, None)

    async def test_happy_path_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["deal_id"] == deal_id
        assert data["ai_generated"] is True
        assert data["status"] == "draft"

    async def test_content_contains_expected_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        content = resp.json()["data"]["content"]
        for key in ("project_overview", "scope_of_work", "deliverables", "timeline", "pricing"):
            assert key in content, f"Missing key: {key}"

    async def test_first_proposal_is_version_1(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["version_number"] == 1

    async def test_second_call_increments_version(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        r1 = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        r2 = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r2.json()["data"]["version_number"] == r1.json()["data"]["version_number"] + 1

    async def test_proposal_appears_in_list(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        gen_resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        proposal_id = gen_resp.json()["data"]["id"]

        list_resp = await client.get("/api/v1/proposals", headers=headers)
        ids = [p["id"] for p in list_resp.json()["data"]]
        assert proposal_id in ids

    async def test_proposal_retrievable_by_id(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        gen_resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers
        )
        proposal_id = gen_resp.json()["data"]["id"]

        get_resp = await client.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["ai_generated"] is True

    async def test_nonexistent_deal_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_other_users_deal_returns_404(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal(client, headers_a)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{uuid.uuid4()}"
        )
        assert resp.status_code == 401

    async def test_tenant_isolation_in_list(self, client: AsyncClient) -> None:
        """Generated proposal from user A is not visible to user B."""
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal(client, headers_a)

        await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}", headers=headers_a
        )

        list_resp = await client.get("/api/v1/proposals", headers=headers_b)
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) == 0


class TestGenerateFromDealEntitlement:
    """Tests that require the strict (entitlement-aware) AI facade."""

    @pytest.fixture(autouse=True)
    def _use_strict_ai(self):
        app.dependency_overrides[get_ai_facade] = lambda: _StrictAIFacade()
        yield
        app.dependency_overrides.pop(get_ai_facade, None)

    async def test_free_plan_returns_402(self, client: AsyncClient) -> None:
        """Newly registered user has no subscription → no AI access → 402."""
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        assert resp.status_code == 402, resp.text

    async def test_free_plan_error_body(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        assert resp.status_code == 402
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "SUBSCRIPTION_REQUIRED"

    async def test_no_proposal_created_on_402(self, client: AsyncClient) -> None:
        """If AI access is denied, no proposal row is written to the DB."""
        headers = await _auth(client)
        deal_id = await _make_deal(client, headers)

        await client.post(
            f"/api/v1/proposals/generate-from-deal/{deal_id}",
            headers=headers,
        )
        list_resp = await client.get("/api/v1/proposals", headers=headers)
        assert len(list_resp.json()["data"]) == 0
