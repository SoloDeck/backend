"""Integration tests for deals CRUD and list filters."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from src.shared.dependencies.ai import get_ai_facade
from tests.conftest import grant_ai_plan

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

    # Truyền `db_session` khi test cần CHẠY AI: `/deals/{id}/qualify` giờ kiểm tra quyền +
    # hạn mức qua `AiUsageService.consume()`, mà user đăng ký mới trong test không có gói
    # nào (test DB không seed bảng gói) → 402.  #Huynh
    if db_session is not None:
        me = await client.get("/api/v1/users/me", headers=headers)
        await grant_ai_plan(db_session, uuid.UUID(me.json()["data"]["id"]))

    return headers


async def _create_client(client: AsyncClient, headers: dict, name: str = "Acme") -> str:
    resp = await client.post(
        "/api/v1/clients", json={"name": name, "status": "prospect"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(
    client: AsyncClient,
    headers: dict,
    title: str = "My Deal",
    stage: str = "new_lead",
    client_id: str | None = None,
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
        resp = await client.post(
            "/api/v1/deals", json={"client_id": client_id, "title": "Deal A"}, headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Deal A"
        assert data["stage"] == "new_lead"

    async def test_unknown_client_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/deals", json={"client_id": str(uuid.uuid4()), "title": "X"}, headers=headers
        )
        assert resp.status_code == 404

    async def test_missing_title_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        client_id = await _create_client(client, headers)
        resp = await client.post("/api/v1/deals", json={"client_id": client_id}, headers=headers)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/deals", json={"client_id": str(uuid.uuid4()), "title": "X"}
        )
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
        p1 = [
            d["id"]
            for d in (await client.get("/api/v1/deals?page=1&page_size=3", headers=headers)).json()[
                "data"
            ]
        ]
        p2 = [
            d["id"]
            for d in (await client.get("/api/v1/deals?page=2&page_size=3", headers=headers)).json()[
                "data"
            ]
        ]
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
        resp = await client.patch(
            f"/api/v1/deals/{uuid.uuid4()}", json={"client_id": str(uuid.uuid4()), "title": "X"}
        )
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


# ---------------------------------------------------------------------------
# AI qualification signal fields in DealResponse
# ---------------------------------------------------------------------------

_AI_FIELDS = [
    "ai_qualification_score",
    "ai_level",
    "is_ai_qualified",
    "ai_qualification_recommendation",
    "ai_qualification_reasoning",
    "ai_qualification_project_type",
    "ai_qualification_budget_signal",
    "ai_qualification_timeline_signal",
    "ai_qualification_urgency_signal",
    "ai_qualification_red_flags",
    "ai_qualification_next_step",
    "ai_qualification_detected_signals",
    "ai_qualification_suggested_actions",
    "ai_qualification_price_range_min",
    "ai_qualification_price_range_max",
]

_MOCK_AI_RESULT = {
    "project_type": "E-commerce website",
    "budget_signal": "HIGH",
    "timeline_signal": "CLEAR",
    "urgency_signal": "MODERATE",
    "red_flags": ["no mockups provided"],
    "suggested_lead_score": "HOT",
    # Điểm giờ được TÍNH TRONG CODE từ bảng phân rã 5 tiêu chí này (tối đa
    # 30/25/20/15/10 = 100), KHÔNG còn tra bảng từ nhãn `suggested_lead_score` mà AI tự
    # dán. Đó chính là lý do bộ chấm điểm cũ không đáng tin: AI nói "HOT" là được 80 điểm,
    # không ai kiểm chứng được vì sao.
    #
    # 25 + 22 + 18 + 10 + 5 = 80.  #Huynh
    "score_breakdown": {
        "scope": {"points": 25, "reason": "Khách nêu rõ hạng mục cần làm."},
        "budget": {"points": 22, "reason": "Khách nói rõ ngân sách."},
        "timeline": {"points": 18, "reason": "Khách nêu deadline cụ thể."},
        "detail": {"points": 10, "reason": "Mô tả tương đối chi tiết."},
        "context": {"points": 5, "reason": "Đến từ kênh inbound."},
    },
    "reasoning": "Strong budget and clear timeline.",
    "next_step": "Reply today to confirm scope and move to quoting.",
    "detected_signals": [
        {"text": "Budget explicitly stated", "is_positive": True},
        {"text": "Timeline is clear", "is_positive": True},
        {"text": "No mockups provided", "is_positive": False},
    ],
    "suggested_actions": [
        "Reply today to confirm scope",
        "Generate AI quote after scope confirmation",
        "Set follow-up reminder in 24 hours",
    ],
    "price_range_min": 10000000,
    "price_range_max": 25000000,
}


def _mock_ai_facade(**overrides):
    facade = AsyncMock()
    facade.qualify_lead.return_value = {**_MOCK_AI_RESULT, **overrides}

    # `last_usage()` là hàm ĐỒNG BỘ (facade thật trả về dict token đã dùng để ghi
    # `ai_cost_records`). Để AsyncMock tự sinh thì nó trả về coroutine, và code gọi
    # `.get("input_tokens")` trên coroutine đó → AttributeError.  #Huynh
    facade.last_usage = MagicMock(return_value=None)
    return facade


async def _create_deal_via_intake(client: AsyncClient, headers: dict) -> str:
    """Submit a public intake and return the resulting deal_id (Celery suppressed)."""
    me = await client.get("/api/v1/users/me", headers=headers)
    token = me.json()["data"]["intake_share_token"]
    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        resp = await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Test Lead", "inquiry_text": "I need a full e-commerce build."},
        )
    assert resp.status_code == 201, resp.text
    deals = await client.get("/api/v1/deals", headers=headers)
    return deals.json()["data"][0]["id"]


class TestDealAIFieldsPresence:
    """All DealResponse endpoints must include all 10 AI fields."""

    async def test_post_deal_includes_all_ai_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "AI Field Check")
        for field in _AI_FIELDS:
            assert field in deal, f"POST /deals missing field: {field}"

    async def test_get_deal_list_includes_all_ai_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _create_deal(client, headers, "List Field Check")
        resp = await client.get("/api/v1/deals", headers=headers)
        deal = resp.json()["data"][0]
        for field in _AI_FIELDS:
            assert field in deal, f"GET /deals missing field: {field}"

    async def test_get_deal_by_id_includes_all_ai_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Single Field Check")
        resp = await client.get(f"/api/v1/deals/{deal['id']}", headers=headers)
        data = resp.json()["data"]
        for field in _AI_FIELDS:
            assert field in data, f"GET /deals/id missing field: {field}"

    async def test_patch_deal_includes_all_ai_fields(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Patch Field Check")
        resp = await client.patch(
            f"/api/v1/deals/{deal['id']}",
            json={"client_id": deal["client_id"], "title": "Updated"},
            headers=headers,
        )
        data = resp.json()["data"]
        for field in _AI_FIELDS:
            assert field in data, f"PATCH /deals/id missing field: {field}"

    async def test_new_deal_ai_fields_are_null(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal = await _create_deal(client, headers, "Null AI Check")
        assert deal["ai_qualification_score"] is None
        assert deal["ai_level"] is None
        assert deal["is_ai_qualified"] is False
        assert deal["ai_qualification_recommendation"] is None
        assert deal["ai_qualification_reasoning"] is None
        assert deal["ai_qualification_red_flags"] is None
        assert deal["ai_qualification_next_step"] is None
        assert deal["ai_qualification_detected_signals"] is None
        assert deal["ai_qualification_suggested_actions"] is None
        assert deal["ai_qualification_price_range_min"] is None
        assert deal["ai_qualification_price_range_max"] is None


class TestDealAIQualificationFields:
    """After qualification, computed fields and signal fields reflect AI output."""

    async def test_qualify_sets_hot_level_and_all_signals(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client, db_session)
        deal_id = await _create_deal_via_intake(client, headers)

        mock_facade = _mock_ai_facade()
        from src.main import app

        app.dependency_overrides[get_ai_facade] = lambda: mock_facade

        try:
            resp = await client.post(
                f"/api/v1/deals/{deal_id}/qualify",
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_ai_facade, None)

        assert resp.status_code == 200, resp.text

        # Re-fetch the deal to verify persisted fields
        deals_resp = await client.get("/api/v1/deals", headers=headers)
        qualified = next(
            (d for d in deals_resp.json()["data"] if d["ai_qualification_score"] is not None),
            None,
        )
        assert qualified is not None, "No deal found with AI score after qualification"
        assert qualified["ai_qualification_score"] == 80
        assert qualified["ai_level"] == "hot"
        assert qualified["is_ai_qualified"] is True
        assert qualified["ai_qualification_recommendation"] == "qualify"
        assert qualified["ai_qualification_reasoning"] == "Strong budget and clear timeline."
        assert qualified["ai_qualification_project_type"] == "E-commerce website"
        assert qualified["ai_qualification_budget_signal"] == "HIGH"
        assert qualified["ai_qualification_timeline_signal"] == "CLEAR"
        assert qualified["ai_qualification_urgency_signal"] == "MODERATE"
        assert qualified["ai_qualification_red_flags"] == ["no mockups provided"]
        assert (
            qualified["ai_qualification_next_step"]
            == "Reply today to confirm scope and move to quoting."
        )
        assert qualified["ai_qualification_suggested_actions"] == [
            "Reply today to confirm scope",
            "Generate AI quote after scope confirmation",
            "Set follow-up reminder in 24 hours",
        ]
        assert qualified["ai_qualification_price_range_min"] == 10000000
        assert qualified["ai_qualification_price_range_max"] == 25000000
        signals = qualified["ai_qualification_detected_signals"]
        assert len(signals) == 3
        assert signals[0] == {"text": "Budget explicitly stated", "is_positive": True}
        assert signals[2] == {"text": "No mockups provided", "is_positive": False}

    async def test_qualify_warm_score_maps_to_warm_level(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client, db_session)
        deal_id = await _create_deal_via_intake(client, headers)

        # Điểm do CODE cộng từ bảng phân rã, không phải do nhãn AI tự dán. Muốn ra WARM
        # thì phải cho một bảng phân rã cộng lại ra 50 — chứ không phải sửa chữ "WARM".
        # 18 + 12 + 10 + 6 + 4 = 50.  #Huynh
        mock_facade = _mock_ai_facade(
            suggested_lead_score="WARM",
            score_breakdown={
                "scope": {"points": 18, "reason": "Phạm vi nêu chung chung."},
                "budget": {"points": 12, "reason": "Khách nói ngân sách mơ hồ."},
                "timeline": {"points": 10, "reason": "Thời gian chưa rõ."},
                "detail": {"points": 6, "reason": "Mô tả sơ sài."},
                "context": {"points": 4, "reason": "Kênh inbound."},
            },
        )

        from src.main import app

        app.dependency_overrides[get_ai_facade] = lambda: mock_facade

        try:
            await client.post(f"/api/v1/deals/{deal_id}/qualify", headers=headers)
        finally:
            app.dependency_overrides.pop(get_ai_facade, None)

        deals_resp = await client.get("/api/v1/deals", headers=headers)
        qualified = next(
            (d for d in deals_resp.json()["data"] if d["ai_qualification_score"] is not None),
            None,
        )
        assert qualified is not None
        assert qualified["ai_qualification_score"] == 50
        assert qualified["ai_level"] == "warm"
        # "Đủ điều kiện báo giá" = KHÔNG PHẢI COLD. Ngưỡng lấy từ `scoring.py`
        # (COLD_THRESHOLD=45), không còn là con số 60 hardcode riêng ở tầng response — hai
        # nguồn sự thật đá nhau là chuyện đã xảy ra một lần rồi.  #Huynh
        assert qualified["is_ai_qualified"] is True  # 50 >= COLD_THRESHOLD (45)

    async def test_qualify_cold_score_maps_to_cold_level_and_pass(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client, db_session)
        deal_id = await _create_deal_via_intake(client, headers)

        # 8 + 0 + 0 + 7 + 5 = 20. Khách không hề nói ngân sách hay thời gian → 0 điểm cả
        # hai tiêu chí đó, và đó chính là thứ người dùng nhìn thấy trên bảng chấm điểm.
        mock_facade = _mock_ai_facade(
            suggested_lead_score="COLD",
            score_breakdown={
                "scope": {"points": 8, "reason": "Chỉ nói chung chung 'cần làm web'."},
                "budget": {"points": 0, "reason": "Khách KHÔNG đề cập ngân sách."},
                "timeline": {"points": 0, "reason": "Khách KHÔNG đề cập thời hạn."},
                "detail": {"points": 7, "reason": "Mô tả rất ngắn."},
                "context": {"points": 5, "reason": "Kênh inbound."},
            },
        )

        from src.main import app

        app.dependency_overrides[get_ai_facade] = lambda: mock_facade

        try:
            await client.post(f"/api/v1/deals/{deal_id}/qualify", headers=headers)
        finally:
            app.dependency_overrides.pop(get_ai_facade, None)

        deals_resp = await client.get("/api/v1/deals", headers=headers)
        qualified = next(
            (d for d in deals_resp.json()["data"] if d["ai_qualification_score"] is not None),
            None,
        )
        assert qualified is not None
        assert qualified["ai_qualification_score"] == 20
        assert qualified["ai_level"] == "cold"
        assert qualified["is_ai_qualified"] is False
        assert qualified["ai_qualification_recommendation"] == "pass"
