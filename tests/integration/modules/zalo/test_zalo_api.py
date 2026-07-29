"""Integration test module Zalo OA (chế độ mock — chạy được không cần OA/URL công khai).

Phủ: kết nối (connect-url → callback → status), ngắt kết nối, webhook gắn zalo_user_id cho
khách, và gửi nhắc kênh zalo THÀNH CÔNG sau khi đã kết nối.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from src.config.settings import settings
from src.infrastructure.database.models import ClientModel

SEND_EMAIL = "src.modules.reminders.application.delivery_service.smtp_send_email"


@pytest.fixture(autouse=True)
def _force_zalo_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ép chế độ mock cho mọi test ở đây — để không phụ thuộc ZALO_MODE trong .env máy dev.
    (Dev đặt real để thử OA thật thì test vẫn phải chạy tất định.)  #Huynh"""
    monkeypatch.setattr(settings, "zalo_mode", "mock")


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"z_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Zalo User",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _connect(client: AsyncClient, headers: dict) -> None:
    """Chạy trọn luồng OAuth ở chế độ mock: lấy URL → rút state → gọi callback."""
    r = await client.get("/api/v1/zalo/connect-url", headers=headers)
    assert r.status_code == 200, r.text
    url = r.json()["data"]["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    cb = await client.get(
        f"/api/v1/zalo/callback?code=mock-auth-code&state={state}", follow_redirects=False
    )
    assert cb.status_code == 303
    assert "zalo=connected" in cb.headers["location"]


class TestKetNoi:
    async def test_connect_roi_status_thanh_connected(self, client: AsyncClient) -> None:
        headers = await _auth(client)

        before = await client.get("/api/v1/zalo/status", headers=headers)
        assert before.json()["data"]["connected"] is False

        await _connect(client, headers)

        after = await client.get("/api/v1/zalo/status", headers=headers)
        data = after.json()["data"]
        assert data["connected"] is True
        assert data["mode"] == "mock"
        assert data["oa_id"] == "mock-oa-000"

    async def test_connect_url_can_dang_nhap(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/zalo/connect-url")
        assert resp.status_code == 401

    async def test_callback_state_bay_thi_ve_fe_kem_co_loi(self, client: AsyncClient) -> None:
        cb = await client.get(
            "/api/v1/zalo/callback?code=x&state=khong-hop-le", follow_redirects=False
        )
        assert cb.status_code == 303
        assert "zalo=error" in cb.headers["location"]

    async def test_ngat_ket_noi(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _connect(client, headers)

        resp = await client.delete("/api/v1/zalo/connection", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["connected"] is False


class TestRealThieuCauHinh:
    """Mode `real` mà thiếu config thì phải nói ngay, đừng đẩy người dùng sang Zalo ăn -14003.

    `env_ignore_empty` khiến biến rỗng rơi về mặc định `""`, nên thiếu cấu hình KHÔNG hề
    làm app nổ lúc khởi động — nó im lặng dựng URL cấp quyền cụt rồi để Zalo từ chối. Đó
    đúng là kiểu hỏng đã tốn cả buổi 24/07 để lần ra.  #Huynh
    """

    async def test_thieu_redirect_uri_thi_bao_loi_ngay(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        headers = await _auth(client)
        monkeypatch.setattr(settings, "zalo_mode", "real")
        monkeypatch.setattr(settings, "zalo_app_id", "123")
        monkeypatch.setattr(settings, "zalo_oauth_redirect_uri", "")

        resp = await client.get("/api/v1/zalo/connect-url", headers=headers)

        assert resp.status_code == 409
        assert "ZALO_OAUTH_REDIRECT_URI" in resp.json()["error"]["message"]

    async def test_thieu_app_id_thi_bao_loi_ngay(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        headers = await _auth(client)
        monkeypatch.setattr(settings, "zalo_mode", "real")
        monkeypatch.setattr(settings, "zalo_app_id", "")
        monkeypatch.setattr(settings, "zalo_oauth_redirect_uri", "https://api/cb")

        resp = await client.get("/api/v1/zalo/connect-url", headers=headers)

        assert resp.status_code == 409

    async def test_du_cau_hinh_thi_tro_sang_zalo_that(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Đủ config thì URL phải trỏ sang Zalo, KHÔNG phải callback giả của mock."""
        headers = await _auth(client)
        monkeypatch.setattr(settings, "zalo_mode", "real")
        monkeypatch.setattr(settings, "zalo_app_id", "123")
        monkeypatch.setattr(settings, "zalo_app_secret", "shh")
        monkeypatch.setattr(
            settings,
            "zalo_oauth_redirect_uri",
            "https://api-staging.solodesk.space/api/v1/zalo/callback",
        )

        resp = await client.get("/api/v1/zalo/connect-url", headers=headers)

        assert resp.status_code == 200
        url = resp.json()["data"]["url"]
        assert url.startswith("https://oauth.zaloapp.com/v4/oa/permission?")
        query = parse_qs(urlparse(url).query)
        # redirect_uri phải có mặt — thiếu nó chính là nguyên nhân sinh ra -14003.
        assert query["redirect_uri"] == ["https://api-staging.solodesk.space/api/v1/zalo/callback"]
        assert query["app_id"] == ["123"]


class TestWebhook:
    async def test_webhook_gan_zalo_user_id_cho_khach(
        self, client: AsyncClient, db_session
    ) -> None:
        headers = await _auth(client)
        await _connect(client, headers)  # user.zalo_oa_app_id = "mock-oa-000"

        phone = "0900001111"
        created = await client.post(
            "/api/v1/clients", json={"name": "Khách", "phone": phone}, headers=headers
        )
        client_id = uuid.UUID(created.json()["data"]["id"])

        body = {
            "oa_id": "mock-oa-000",
            "sender": {"id": "follower-999"},
            "info": {"phone": phone},
        }
        wh = await client.post("/api/v1/zalo/webhook", json=body)
        assert wh.status_code == 200

        row = await db_session.get(ClientModel, client_id)
        await db_session.refresh(row)
        assert row.zalo_user_id == "follower-999"

    async def test_webhook_oa_la_khong_khop_thi_bo_qua_van_200(
        self, client: AsyncClient
    ) -> None:
        # Không có OA nào ứng với oa_id này → xử lý im lặng, vẫn 200 để Zalo không retry.
        wh = await client.post(
            "/api/v1/zalo/webhook",
            json={"oa_id": "khong-ton-tai", "sender": {"id": "x"}, "info": {"phone": "0900"}},
        )
        assert wh.status_code == 200


class TestGuiNhacZalo:
    async def test_da_ket_noi_thi_gui_kenh_zalo_thanh_cong(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await _connect(client, headers)

        c = await client.post(
            "/api/v1/clients", json={"name": "Khách", "email": "k@example.com"}, headers=headers
        )
        deal = await client.post(
            "/api/v1/deals",
            json={"client_id": c.json()["data"]["id"], "title": "Deal"},
            headers=headers,
        )
        reminder = await client.post(
            "/api/v1/reminders",
            json={
                "target_type": "deal",
                "target_id": deal.json()["data"]["id"],
                "reminder_type": "follow_up",
                "channel": "zalo",
                "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "message_preview": "Chào anh, em nhắc lịch ạ.",
            },
            headers=headers,
        )
        reminder_id = reminder.json()["data"]["id"]

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder_id}/send", headers=headers)

        data = resp.json()["data"]
        assert data["status"] == "sent"
        assert data["delivered"] is True
        send_email.assert_not_awaited()
