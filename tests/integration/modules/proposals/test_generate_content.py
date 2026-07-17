"""Integration tests for POST /proposals/{id}/generate."""

import uuid

import pytest
from httpx import AsyncClient

from src.main import app
from src.shared.dependencies.ai import get_ai_facade
from src.shared.exceptions.domain import EntitlementError
from tests.conftest import grant_ai_plan

# ---------------------------------------------------------------------------
# Fake AI facades (same pattern as test_generate_from_deal.py)
# ---------------------------------------------------------------------------

_FAKE_CONTENT = {
    "project_overview": "Rebuild the client portal from scratch.",
    "scope_of_work": ["Auth module", "Dashboard", "Reporting"],
    "deliverables": ["Source code", "Deployed app", "Docs"],
    "timeline": "6 weeks",
    "pricing": "30,000,000 VND",
    "payment_terms": "50% upfront, 50% on delivery",
    "assumptions": "Client provides brand guidelines",
}


class _PermissiveAIFacade:
    async def generate_proposal(
        self, *, deal_data, client_data, user_profile, template, user_can_use_ai
    ):
        return _FAKE_CONTENT

    def last_usage(self, module):
        """Facade thật trả về token đã dùng để ghi `ai_cost_records`. Stub thì không tốn
        đồng nào, nên trả None — dịch vụ hiểu là "không có gì để ghi".  #Huynh"""
        return None


class _StrictAIFacade:
    async def generate_proposal(
        self, *, deal_data, client_data, user_profile, template, user_can_use_ai
    ):
        if not user_can_use_ai:
            raise EntitlementError(
                "Your plan does not include AI features. Upgrade to Pro.",
                entitlement="can_use_ai",
            )
        return _FAKE_CONTENT

    def last_usage(self, module):
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _auth(client: AsyncClient, db_session=None) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text

    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    # Cấp gói CÓ AI. Endpoint AI giờ kiểm tra quyền + hạn mức qua `AiUsageService.consume()`
    # — user đăng ký mới trong test không có gói nào (test DB không seed bảng gói), nên mọi
    # lệnh gọi AI trả 402. Việc CHẶN 402/429 có class test riêng (`...Entitlement`) và class
    # đó CỐ Ý không gọi hàm này.  #Huynh
    if db_session is not None:
        me = await client.get("/api/v1/users/me", headers=headers)
        await grant_ai_plan(db_session, uuid.UUID(me.json()["data"]["id"]))

    return headers


async def _make_proposal(http: AsyncClient, headers: dict) -> dict:
    c = await http.post(
        "/api/v1/clients", json={"name": "Acme", "status": "prospect"}, headers=headers
    )
    assert c.status_code == 201, c.text
    d = await http.post(
        "/api/v1/deals",
        json={"client_id": c.json()["data"]["id"], "title": "Website Project"},
        headers=headers,
    )
    assert d.status_code == 201, d.text
    p = await http.post(
        "/api/v1/proposals",
        json={
            "deal_id": d.json()["data"]["id"],
            # có giá cụ thể để chuyển sang "sent" được (báo giá không giá bị chặn 409).
            "content": {"body": "initial", "pricing": {"total": 5_000_000, "currency": "VND"}},
        },
        headers=headers,
    )
    assert p.status_code == 201, p.text
    return p.json()["data"]


# ---------------------------------------------------------------------------
# POST /proposals/{id}/generate
# ---------------------------------------------------------------------------


class TestGenerateProposalContent:
    @pytest.fixture(autouse=True)
    def _use_permissive_ai(self):
        app.dependency_overrides[get_ai_facade] = lambda: _PermissiveAIFacade()
        yield
        app.dependency_overrides.pop(get_ai_facade, None)

    async def test_happy_path_returns_200(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["id"] == proposal["id"]
        assert data["ai_generated"] is True

    async def test_content_is_replaced_with_ai_output(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        content = resp.json()["data"]["content"]
        assert content["project_overview"] == _FAKE_CONTENT["project_overview"]
        assert content["scope_of_work"] == _FAKE_CONTENT["scope_of_work"]

    async def test_content_persists_on_get(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers)

        await client.post(f"/api/v1/proposals/{proposal['id']}/generate", headers=headers)

        get_resp = await client.get(f"/api/v1/proposals/{proposal['id']}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["ai_generated"] is True
        assert "project_overview" in get_resp.json()["data"]["content"]

    async def test_generate_on_sent_proposal_returns_409(
        self, client: AsyncClient, db_session
    ) -> None:
        """AI generation is only allowed on draft proposals."""
        headers = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers)

        await client.patch(
            f"/api/v1/proposals/{proposal['id']}/status",
            json={"status": "sent"},
            headers=headers,
        )

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"

    async def test_generate_on_accepted_proposal_returns_409(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers)

        await client.patch(
            f"/api/v1/proposals/{proposal['id']}/status", json={"status": "sent"}, headers=headers
        )
        await client.patch(
            f"/api/v1/proposals/{proposal['id']}/status",
            json={"status": "accepted"},
            headers=headers,
        )

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_nonexistent_proposal_returns_404(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(
            f"/api/v1/proposals/{uuid.uuid4()}/generate",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_other_users_proposal_returns_404(self, client: AsyncClient, db_session) -> None:
        headers_a = await _auth(client, db_session)
        headers_b = await _auth(client, db_session)
        proposal = await _make_proposal(client, headers_a)

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session) -> None:
        resp = await client.post(f"/api/v1/proposals/{uuid.uuid4()}/generate")
        assert resp.status_code == 401


class TestGenerateProposalContentEntitlement:
    @pytest.fixture(autouse=True)
    def _use_strict_ai(self):
        app.dependency_overrides[get_ai_facade] = lambda: _StrictAIFacade()
        yield
        app.dependency_overrides.pop(get_ai_facade, None)

    async def test_free_plan_returns_402(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        proposal = await _make_proposal(client, headers)

        resp = await client.post(
            f"/api/v1/proposals/{proposal['id']}/generate",
            headers=headers,
        )
        assert resp.status_code == 402

    async def test_content_unchanged_on_402(self, client: AsyncClient) -> None:
        """If AI access is denied, the existing proposal content must not be modified."""
        headers = await _auth(client)
        proposal = await _make_proposal(client, headers)
        original_content = proposal["content"]

        await client.post(f"/api/v1/proposals/{proposal['id']}/generate", headers=headers)

        get_resp = await client.get(f"/api/v1/proposals/{proposal['id']}", headers=headers)
        assert get_resp.json()["data"]["content"] == original_content
        assert get_resp.json()["data"]["ai_generated"] is False
