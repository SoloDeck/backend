"""Integration tests for POST /api/v1/ai/leads/qualify.

Uses real PostgreSQL (rolled back per test). The AI chain is mocked so tests
never call the real Gemini API.

Endpoint này TRƯỚC ĐÂY LÀ CÔNG KHAI — không đăng nhập vẫn gọi được, nghĩa là bất kỳ ai
biết URL cũng đốt được hạn mức Groq của chúng ta (mỗi lệnh gọi là tiền thật). Giờ nó đòi
đăng nhập và trừ hạn mức qua `AiUsageService.consume()`, nên mọi test ở đây phải đăng nhập
và có gói dùng được AI.  #Huynh
"""

import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.conftest import grant_ai_plan

ENDPOINT = "/api/v1/ai/leads/qualify"

VALID_CHAIN_RESULT = {
    "project_type": "E-commerce website",
    "budget_signal": "50-80 million VND",
    "timeline_signal": "3 months",
    "urgency_signal": "Medium",
    "red_flags": [],
    "suggested_lead_score": "HOT",
    "reasoning": "Clear project, budget and timeline provided.",
}


def _patch_chain(result: dict | None = None, side_effect=None):
    """Patch LeadQualifier.run so tests never hit the real Gemini API."""
    mock = AsyncMock(return_value=result or VALID_CHAIN_RESULT, side_effect=side_effect)
    return patch("src.ai.lead_qualifier.api.router.LeadQualifier.run", mock)


async def _auth(client: AsyncClient, db_session) -> dict:
    """Đăng ký một user và cấp gói có AI."""
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

    me = await client.get("/api/v1/users/me", headers=headers)
    await grant_ai_plan(db_session, uuid.UUID(me.json()["data"]["id"]))
    return headers


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


class TestQualifyLeadSuccess:
    async def test_returns_200_with_envelope(self, client: AsyncClient, db_session) -> None:
        with _patch_chain():
            headers = await _auth(client, db_session)
            resp = await client.post(
                ENDPOINT, json={"inquiry_text": "Need a website"}, headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == 200
        assert "timestamp" in body
        assert "data" in body

    async def test_data_contains_all_fields(self, client: AsyncClient, db_session) -> None:
        with _patch_chain():
            headers = await _auth(client, db_session)
            resp = await client.post(
                ENDPOINT, json={"inquiry_text": "Need a website"}, headers=headers
            )

        data = resp.json()["data"]
        for field in (
            "project_type",
            "budget_signal",
            "timeline_signal",
            "urgency_signal",
            "red_flags",
            "suggested_lead_score",
            "reasoning",
        ):
            assert field in data, f"Missing field: {field}"

    async def test_data_values_match_chain_output(self, client: AsyncClient, db_session) -> None:
        with _patch_chain():
            headers = await _auth(client, db_session)
            resp = await client.post(
                ENDPOINT, json={"inquiry_text": "Need a website"}, headers=headers
            )

        data = resp.json()["data"]
        assert data["project_type"] == "E-commerce website"
        assert data["suggested_lead_score"] == "HOT"
        assert data["red_flags"] == []

    async def test_with_realistic_vietnamese_inquiry(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client, db_session)
        result = {**VALID_CHAIN_RESULT, "suggested_lead_score": "WARM"}
        with _patch_chain(result):
            resp = await client.post(
                ENDPOINT,
                json={
                    "inquiry_text": (
                        "Tôi cần xây dựng website bán hàng thời trang, "
                        "tích hợp VNPay, ngân sách 50-80 triệu, deadline 3 tháng."
                    )
                },
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["suggested_lead_score"] == "WARM"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestQualifyLeadValidation:
    async def test_missing_inquiry_text_returns_422(self, client: AsyncClient, db_session) -> None:
        headers = await _auth(client, db_session)
        resp = await client.post(ENDPOINT, json={}, headers=headers)
        assert resp.status_code == 422
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 422

    async def test_empty_body_returns_422(self, client: AsyncClient, db_session) -> None:
        auth = await _auth(client, db_session)
        resp = await client.post(
            ENDPOINT, content=b"", headers={**auth, "Content-Type": "application/json"}
        )
        assert resp.status_code == 422

    async def test_wrong_content_type_returns_422(self, client: AsyncClient, db_session) -> None:
        auth = await _auth(client, db_session)
        resp = await client.post(
            ENDPOINT,
            content=b"inquiry_text=hello",
            headers={**auth, "Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestQualifyLeadErrors:
    async def test_chain_exception_returns_502(self, client: AsyncClient, db_session) -> None:
        with _patch_chain(side_effect=RuntimeError("Gemini unavailable")):
            headers = await _auth(client, db_session)
            resp = await client.post(
                ENDPOINT, json={"inquiry_text": "Need a website"}, headers=headers
            )

        assert resp.status_code == 502
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == 502
