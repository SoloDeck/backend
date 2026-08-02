"""Integration tests for reminders CRUD and filters."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

# Chặn SMTP thật. `.env` đang trỏ vào Gmail bằng app password thật, nên thiếu dòng patch
# này là chạy test một lần gửi email thật ra ngoài.  #Huynh
SEND_EMAIL = "src.modules.reminders.application.delivery_service.smtp_send_email"

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


async def _make_deal_id(client: AsyncClient, headers: dict, client_email: str | None = None) -> str:
    payload: dict = {"name": "Client", "status": "prospect"}
    if client_email:
        payload["email"] = client_email
    c = await client.post("/api/v1/clients", json=payload, headers=headers)
    d = await client.post(
        "/api/v1/deals",
        json={"client_id": c.json()["data"]["id"], "title": "Deal"},
        headers=headers,
    )
    return d.json()["data"]["id"]


def _reminder_payload(
    target_id: str, target_type: str = "deal", reminder_type: str = "follow_up"
) -> dict:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "reminder_type": reminder_type,
        "channel": "email",
        "scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "message_preview": "Don't forget!",
    }


async def _create_reminder(client: AsyncClient, headers: dict, target_id: str, **kwargs) -> dict:
    resp = await client.post(
        "/api/v1/reminders", json=_reminder_payload(target_id, **kwargs), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /reminders
# ---------------------------------------------------------------------------


class TestCreateReminder:
    async def test_creates_reminder_returns_201(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.post(
            "/api/v1/reminders", json=_reminder_payload(deal_id), headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["target_type"] == "deal"
        assert data["status"] == "pending"

    async def test_missing_required_fields_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post("/api/v1/reminders", json={"target_type": "deal"}, headers=headers)
        assert resp.status_code == 422

    async def test_invalid_channel_returns_422_not_500(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.post(
            "/api/v1/reminders",
            json=_reminder_payload(deal_id) | {"channel": "sms"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_invalid_reminder_type_returns_422_not_500(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.post(
            "/api/v1/reminders",
            json=_reminder_payload(deal_id, reminder_type="not_a_real_type"),
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/reminders", json=_reminder_payload(str(uuid.uuid4())))
        assert resp.status_code == 401

    async def test_past_scheduled_at_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        payload = _reminder_payload(deal_id)
        payload["scheduled_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        resp = await client.post("/api/v1/reminders", json=payload, headers=headers)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /reminders
# ---------------------------------------------------------------------------


class TestListReminders:
    async def test_returns_own_reminders(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        resp = await client.get("/api/v1/reminders", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    async def test_status_filter_pending(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        r = await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        # Cancel one
        await client.delete(f"/api/v1/reminders/{r['id']}", headers=headers)
        resp = await client.get("/api/v1/reminders?status=pending", headers=headers)
        data = resp.json()["data"]
        assert all(r["status"] == "pending" for r in data)

    async def test_status_filter_cancelled(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        r = await _create_reminder(client, headers, deal_id)
        await _create_reminder(client, headers, deal_id)
        await client.delete(f"/api/v1/reminders/{r['id']}", headers=headers)
        resp = await client.get("/api/v1/reminders?status=cancelled", headers=headers)
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "cancelled"

    async def test_target_type_filter_deal(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id, target_type="deal")
        c = await client.post(
            "/api/v1/clients", json={"name": "X", "status": "prospect"}, headers=headers
        )
        await _create_reminder(client, headers, c.json()["data"]["id"], target_type="client")
        resp = await client.get("/api/v1/reminders?target_type=deal", headers=headers)
        data = resp.json()["data"]
        assert all(r["target_type"] == "deal" for r in data)
        assert len(data) == 1

    async def test_target_type_filter_excludes_others(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        await _create_reminder(client, headers, deal_id, target_type="deal")
        resp = await client.get("/api/v1/reminders?target_type=client", headers=headers)
        assert len(resp.json()["data"]) == 0

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        await _create_reminder(client, headers_a, deal_id)
        resp = await client.get("/api/v1/reminders", headers=headers_b)
        assert len(resp.json()["data"]) == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/reminders")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /reminders/{id}
# ---------------------------------------------------------------------------


class TestGetReminder:
    async def test_returns_reminder(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == reminder["id"]

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/reminders/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/reminders/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /reminders/{id}
# ---------------------------------------------------------------------------


class TestUpdateReminder:
    async def test_updates_message_preview(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        payload = _reminder_payload(deal_id)
        payload["message_preview"] = "Updated message"
        resp = await client.patch(
            f"/api/v1/reminders/{reminder['id']}", json=payload, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["message_preview"] == "Updated message"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        resp = await client.patch(
            f"/api/v1/reminders/{uuid.uuid4()}", json=_reminder_payload(deal_id), headers=headers
        )
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.patch(
            f"/api/v1/reminders/{reminder['id']}",
            json=_reminder_payload(deal_id),
            headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        deal_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/v1/reminders/{uuid.uuid4()}", json=_reminder_payload(deal_id)
        )
        assert resp.status_code == 401

    async def test_partial_update_does_not_require_full_payload(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id, reminder_type="payment_due")

        resp = await client.patch(
            f"/api/v1/reminders/{reminder['id']}",
            json={"message_preview": "Just a nudge"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["message_preview"] == "Just a nudge"
        assert body["reminder_type"] == "payment_due"
        assert body["channel"] == "email"

    async def test_invalid_channel_returns_422_not_500(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)

        resp = await client.patch(
            f"/api/v1/reminders/{reminder['id']}",
            json={"channel": "sms"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_past_scheduled_at_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)

        resp = await client.patch(
            f"/api/v1/reminders/{reminder['id']}",
            json={"scheduled_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /reminders/{id}
# ---------------------------------------------------------------------------


class TestCancelReminder:
    async def test_cancels_reminder(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)
        reminder = await _create_reminder(client, headers, deal_id)
        resp = await client.delete(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert resp.status_code == 200
        # Verify it's cancelled
        get_resp = await client.get(f"/api/v1/reminders/{reminder['id']}", headers=headers)
        assert get_resp.json()["data"]["status"] == "cancelled"

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.delete(f"/api/v1/reminders/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a)
        reminder = await _create_reminder(client, headers_a, deal_id)
        resp = await client.delete(f"/api/v1/reminders/{reminder['id']}", headers=headers_b)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/reminders/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /reminders/{id}/send — bấm "Gửi ngay", không đợi tới giờ đã hẹn
# ---------------------------------------------------------------------------


class TestSendReminderNow:
    async def test_gui_email_cho_khach_va_chuyen_sang_sent(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers, client_email="khach@example.com")
        reminder = await _create_reminder(client, headers, deal_id)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["delivered"] is True
        assert data["status"] == "sent"
        assert data["reminder"]["status"] == "sent"
        assert send_email.await_args.kwargs["to"] == "khach@example.com"

    async def test_khach_chua_co_email_thi_bao_ly_do_chu_khong_500(
        self, client: AsyncClient
    ) -> None:
        """Khách không có email là chuyện thường ngày, không phải lỗi hệ thống."""
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers)  # cố ý không có email
        reminder = await _create_reminder(client, headers, deal_id)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["delivered"] is False
        assert data["status"] == "failed"
        assert "chưa có email" in data["detail"]
        send_email.assert_not_awaited()

    async def test_gui_lan_hai_thi_khong_gui_lai(self, client: AsyncClient) -> None:
        """Bấm hai lần không được ra hai email cho khách."""
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers, client_email="khach@example.com")
        reminder = await _create_reminder(client, headers, deal_id)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)
            resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["delivered"] is False
        assert send_email.await_count == 1

    async def test_kenh_zalo_chua_ket_noi_thi_failed_chu_khong_gia_vo_da_gui(
        self, client: AsyncClient
    ) -> None:
        """Freelancer chưa kết nối Zalo OA → gửi kênh zalo ra 'failed' + báo thẳng, KHÔNG giả
        'đã gửi'. (Đã kết nối rồi thì gửi thật — phủ ở test_zalo_api.py.)"""
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers, client_email="khach@example.com")
        payload = _reminder_payload(deal_id)
        payload["channel"] = "zalo"
        created = await client.post("/api/v1/reminders", json=payload, headers=headers)
        reminder_id = created.json()["data"]["id"]

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder_id}/send", headers=headers)

        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["delivered"] is False
        assert "chưa kết nối Zalo OA" in data["detail"]
        send_email.assert_not_awaited()

    async def test_kenh_in_app_khong_dung_toi_email(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers, client_email="khach@example.com")
        payload = _reminder_payload(deal_id)
        payload["channel"] = "in_app"
        created = await client.post("/api/v1/reminders", json=payload, headers=headers)
        reminder_id = created.json()["data"]["id"]

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder_id}/send", headers=headers)

        assert resp.json()["data"]["status"] == "sent"
        send_email.assert_not_awaited()

    async def test_reminder_da_huy_thi_khong_gui(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        deal_id = await _make_deal_id(client, headers, client_email="khach@example.com")
        reminder = await _create_reminder(client, headers, deal_id)
        await client.delete(f"/api/v1/reminders/{reminder['id']}", headers=headers)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)

        assert resp.json()["data"]["status"] == "cancelled"
        send_email.assert_not_awaited()

    async def test_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(f"/api/v1/reminders/{uuid.uuid4()}/send", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        """Không ai được bấm gửi lời nhắc của người khác."""
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        deal_id = await _make_deal_id(client, headers_a, client_email="khach@example.com")
        reminder = await _create_reminder(client, headers_a, deal_id)

        with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
            resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers_b)

        assert resp.status_code == 404
        send_email.assert_not_awaited()

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/reminders/{uuid.uuid4()}/send")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET/PATCH /reminders/rules — quy tắc nhắc tự động
# ---------------------------------------------------------------------------


class TestReminderRules:
    async def test_lan_dau_goi_tu_sinh_du_nam_quy_tac(self, client: AsyncClient) -> None:
        """Sinh lười ở đây chứ không backfill trong migration — user đăng ký hôm nay vẫn
        có đủ quy tắc mà không ai phải nhớ chạy lại script."""
        headers = await _auth(client)
        resp = await client.get("/api/v1/reminders/rules", headers=headers)

        assert resp.status_code == 200, resp.text
        rules = resp.json()["data"]
        assert [r["rule_type"] for r in rules] == [
            "proposal_follow_up",
            "contract_signing_nudge",
            "payment_due",
            "payment_overdue",
            "re_engagement",
        ]

    async def test_tai_ket_noi_mac_dinh_tat_con_lai_bat(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        rules = (await client.get("/api/v1/reminders/rules", headers=headers)).json()["data"]
        by_type = {r["rule_type"]: r for r in rules}

        assert by_type["re_engagement"]["is_enabled"] is False
        assert by_type["payment_due"]["is_enabled"] is True

    async def test_moi_quy_tac_mac_dinh_CHO_DUYET(self, client: AsyncClient) -> None:
        """Bật tự gửi phải là hành động có ý thức — nó cho phép email khách hàng thật."""
        headers = await _auth(client)
        rules = (await client.get("/api/v1/reminders/rules", headers=headers)).json()["data"]

        assert all(r["auto_send"] is False for r in rules)

    async def test_goi_hai_lan_khong_sinh_trung(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await client.get("/api/v1/reminders/rules", headers=headers)
        rules = (await client.get("/api/v1/reminders/rules", headers=headers)).json()["data"]

        assert len(rules) == 5

    async def test_sua_duoc_quy_tac(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            "/api/v1/reminders/rules/payment_due",
            json={"offset_days": 7, "auto_send": True, "channel": "email"},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["offset_days"] == 7
        assert data["auto_send"] is True
        assert data["channel"] == "email"

    async def test_sua_duoc_ngay_ca_khi_chua_tung_GET(self, client: AsyncClient) -> None:
        """Đừng bắt người dùng GET một lần cho có rồi mới PATCH được."""
        headers = await _auth(client)
        resp = await client.patch(
            "/api/v1/reminders/rules/payment_overdue", json={"is_enabled": False}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_enabled"] is False

    async def test_quy_tac_khong_lap_thi_tu_choi_dat_lap(self, client: AsyncClient) -> None:
        """Nhắc mãi một báo giá khách đã lờ đi thì không phải chăm sóc mà là làm phiền."""
        headers = await _auth(client)
        resp = await client.patch(
            "/api/v1/reminders/rules/proposal_follow_up",
            json={"repeat_every_days": 3},
            headers=headers,
        )

        # ValidationError của domain map sang 422 trong toàn bộ codebase này.
        assert resp.status_code == 422, resp.text

    async def test_so_ngay_vo_ly_bi_tu_choi(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            "/api/v1/reminders/rules/payment_due", json={"offset_days": 9999}, headers=headers
        )

        assert resp.status_code == 422, resp.text

    async def test_loai_quy_tac_khong_ton_tai(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.patch(
            "/api/v1/reminders/rules/khong_ton_tai", json={"is_enabled": False}, headers=headers
        )

        assert resp.status_code == 422, resp.text

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        """Sửa quy tắc của mình không được đụng tới quy tắc người khác."""
        headers_a = await _auth(client)
        headers_b = await _auth(client)
        await client.patch(
            "/api/v1/reminders/rules/payment_due", json={"offset_days": 30}, headers=headers_a
        )

        rules_b = (await client.get("/api/v1/reminders/rules", headers=headers_b)).json()["data"]
        payment_due = next(r for r in rules_b if r["rule_type"] == "payment_due")
        assert payment_due["offset_days"] == 3

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/reminders/rules")).status_code == 401


class TestXemTruocThu:
    """`POST /reminders/preview` — dựng thử lá thư, không lưu và không gửi.

    Vì sao phải để server dựng: thư nhắc thanh toán nay có mã QR và số tài khoản. Frontend
    vẽ lại một bản "gần giống" thì sớm muộn cũng lệch với thư thật — mà lệch ở đây nghĩa là
    freelancer duyệt một đằng, khách nhận một nẻo, và tiền có thể chuyển nhầm chỗ.  #Huynh
    """

    async def test_nhac_thanh_toan_thi_thu_co_so_tai_khoan_va_ma_QR(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        await client.patch(
            "/api/v1/users/me/freelancer-profile",
            json={
                "bank_code": "970436",
                "bank_account_number": "1027123456",
                "bank_account_holder": "NGUYEN VAN A",
            },
            headers=headers,
        )
        deal_id = await _make_deal_id(client, headers)

        resp = await client.post(
            "/api/v1/reminders/preview",
            json={
                "reminder_type": "payment_overdue",
                "target_type": "deal",
                "target_id": deal_id,
                "message": "Chào anh, mình nhắc khoản thanh toán ạ.",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert "1027123456" in data["html"]
        assert "NGUYEN VAN A" in data["html"]
        # QR nhúng dạng data-URI cho trình duyệt (thư thật thì đính kèm `cid:`).
        assert "data:image/png;base64," in data["html"]
        assert "Nhắc thanh toán" in data["subject"] or "quá hạn" in data["subject"].lower()

    async def test_thu_hoi_tham_KHONG_dinh_so_tai_khoan(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        await client.patch(
            "/api/v1/users/me/freelancer-profile",
            json={"bank_code": "970436", "bank_account_number": "1027123456"},
            headers=headers,
        )
        deal_id = await _make_deal_id(client, headers)

        resp = await client.post(
            "/api/v1/reminders/preview",
            json={
                "reminder_type": "follow_up",
                "target_type": "deal",
                "target_id": deal_id,
                "message": "Chào anh, dự án tới đâu rồi ạ?",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert "1027123456" not in resp.json()["data"]["html"]

    async def test_khong_dang_nhap_thi_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/reminders/preview",
            json={
                "reminder_type": "follow_up",
                "target_type": "deal",
                "target_id": str(uuid.uuid4()),
                "message": "x",
            },
        )
        assert resp.status_code == 401
