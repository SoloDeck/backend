"""Gửi hóa đơn thì tự đặt lời nhắc "Nhắc thanh toán đến hạn" ở tab Nhắc nhở, THEO quy tắc của user.

Chạy trên PostgreSQL thật: chỗ cần kiểm là lời nhắc thật sự nằm trong bảng `reminders` với thông số
lấy từ quy tắc "Nhắc trước khi hóa đơn tới hạn" (số ngày, giờ, kênh, công tắc), và bị
hủy/cập nhật đúng lúc — mock repo không chứng minh được điều đó.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers

# `/send` của hóa đơn dùng `src.shared.email.smtp.send_email`; khâu giao lời nhắc dùng bản đã nhập
# vào module delivery_service.
SEND_INVOICE_EMAIL = "src.shared.email.smtp.send_email"
SEND_REMINDER_EMAIL = "src.modules.reminders.application.delivery_service.smtp_send_email"

DEAL_TITLE = "English center"
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
ASK = {"schedule_payment_reminder": True}


async def _new_invoice(
    http: AsyncClient,
    headers: dict,
    *,
    client_email: str | None = "khach@example.com",
    due_in_days: int = 14,
) -> dict:
    payload: dict = {"name": "Nguyễn Văn Mười", "status": "prospect"}
    if client_email:
        payload["email"] = client_email
    client_obj = (await http.post("/api/v1/clients", json=payload, headers=headers)).json()["data"]
    deal = await http.post(
        "/api/v1/deals",
        json={"client_id": client_obj["id"], "title": DEAL_TITLE, "estimated_value": "1000"},
        headers=headers,
    )
    assert deal.status_code == 201, deal.text
    resp = await http.post(
        "/api/v1/invoices",
        json={
            "client_id": client_obj["id"],
            "deal_id": deal.json()["data"]["id"],
            "subtotal": str(Decimal("100.00")),
            "tax_rate": "0",
            "due_date": (date.today() + timedelta(days=due_in_days)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _send(http: AsyncClient, headers: dict, invoice_id: str, body: dict | None):
    with patch(SEND_INVOICE_EMAIL, new=AsyncMock()):
        return await http.post(f"/api/v1/invoices/{invoice_id}/send", json=body, headers=headers)


async def _invoice_reminders(http: AsyncClient, headers: dict, invoice_id: str) -> list[dict]:
    resp = await http.get("/api/v1/reminders", params={"target_type": "invoice"}, headers=headers)
    assert resp.status_code == 200, resp.text
    return [r for r in resp.json()["data"] if r["target_id"] == invoice_id]


async def _rule(http: AsyncClient, headers: dict, **changes) -> dict:
    """Quy tắc "Nhắc trước khi hóa đơn tới hạn" của user (tự tạo bộ mặc định nếu chưa có)."""
    if changes:
        resp = await http.patch(
            "/api/v1/reminders/rules/payment_due", json=changes, headers=headers
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]
    resp = await http.get("/api/v1/reminders/rules", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(r for r in resp.json()["data"] if r["rule_type"] == "payment_due")


def _expected_time(due: str, days: int, hour: int) -> datetime:
    day = date.fromisoformat(due) - timedelta(days=days)
    return datetime.combine(day, time(hour), tzinfo=ICT).astimezone(UTC)


async def _pay(http: AsyncClient, headers: dict, invoice_id: str, amount: str):
    return await http.post(
        f"/api/v1/invoices/{invoice_id}/payments",
        json={
            "amount": amount,
            "payment_date": date.today().isoformat(),
            "payment_method": "bank_transfer",
        },
        headers=headers,
    )


async def test_quy_tac_mac_dinh_thi_dat_loi_nhac_cho_duyet_theo_dung_thong_so(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    rule = await _rule(client, headers)
    invoice = await _new_invoice(client, headers)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.status_code == 200, resp.text
    sent = resp.json()["data"]
    assert sent["status"] == "sent"
    reminders = await _invoice_reminders(client, headers, invoice["id"])
    assert len(reminders) == 1
    reminder = reminders[0]
    assert reminder["reminder_type"] == "payment_due"
    assert reminder["status"] == "pending"
    # Mọi thông số đến từ quy tắc, không có luật riêng.
    assert reminder["channel"] == rule["channel"]
    expected = _expected_time(invoice["due_date"], rule["offset_days"], rule["send_at_hour"])
    assert datetime.fromisoformat(reminder["scheduled_at"]) == expected
    # Luôn nằm chờ duyệt (quy tắc không còn công tắc "tự gửi"); có nhãn "Tự động" ở tab Nhắc nhở.
    assert rule["auto_send"] is False
    assert reminder["requires_approval"] is True
    assert reminder["created_by_rule"] is True
    # Nội dung là mẫu của quy tắc, đã điền thông tin thật.
    assert "Nguyễn Văn Mười" in reminder["message_preview"]
    assert invoice["invoice_number"] in reminder["message_preview"]
    assert "{" not in reminder["message_preview"]
    # Phản hồi của lệnh gửi cho web biết đã lên lịch, mấy ngày, có chờ duyệt không.
    info = sent["payment_reminder"]
    assert info["scheduled"] is True and info["reason"] is None
    assert info["days_before_due"] == rule["offset_days"]
    assert info["requires_approval"] is True
    assert datetime.fromisoformat(info["scheduled_at"]) == expected


async def test_doi_quy_tac_thi_loi_nhac_doi_theo(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    await _rule(
        client,
        headers,
        offset_days=5,
        send_at_hour=14,
        channel="both",
        message_template="Gửi {client_name}: {invoice_number} hạn {due_date}.",
    )
    invoice = await _new_invoice(client, headers)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.status_code == 200, resp.text
    reminder = (await _invoice_reminders(client, headers, invoice["id"]))[0]
    assert datetime.fromisoformat(reminder["scheduled_at"]) == _expected_time(
        invoice["due_date"], 5, 14
    )
    assert reminder["channel"] == "both"
    assert reminder["requires_approval"] is True  # không có đường tự gửi cho khách
    due = date.fromisoformat(invoice["due_date"])
    assert reminder["message_preview"] == (
        f"Gửi Nguyễn Văn Mười: {invoice['invoice_number']} hạn {due:%d/%m/%Y}."
    )
    assert resp.json()["data"]["payment_reminder"]["requires_approval"] is True


async def test_client_cu_gui_auto_send_bat_thi_lenh_bi_bo_qua_va_van_cho_duyet(
    client: AsyncClient,
) -> None:
    """Công tắc "tự gửi" đã bỏ: gửi `auto_send=True` lên không lỗi nhưng không bật được gì."""
    headers = await _auth_headers(client)
    rule = await _rule(client, headers, auto_send=True)
    assert rule["auto_send"] is False
    invoice = await _new_invoice(client, headers)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.status_code == 200, resp.text
    reminder = (await _invoice_reminders(client, headers, invoice["id"]))[0]
    assert reminder["requires_approval"] is True


async def test_nguoi_dung_cu_con_cot_tu_gui_bat_van_khong_co_duong_tu_gui(
    client: AsyncClient, db_session
) -> None:
    """Người dùng cũ từng bật "Tự động gửi" (cột trong CSDL còn True). Công tắc đã bỏ nên cả hai
    đường tạo lời nhắc — gửi hóa đơn và bộ quét hằng ngày — đều để lời nhắc chờ duyệt, và phản hồi
    quy tắc nói False."""
    from sqlalchemy import select, update

    from src.infrastructure.database.models import (
        InvoiceModel,
        ReminderModel,
        ReminderRuleModel,
    )
    from src.modules.reminders.application.auto_scheduler import AutoReminderScheduler

    headers = await _auth_headers(client)
    await _rule(client, headers)  # sinh bộ quy tắc mặc định
    await db_session.execute(update(ReminderRuleModel).values(auto_send=True))
    assert (await _rule(client, headers))["auto_send"] is False

    # Đường 1: gửi hóa đơn.
    invoice = await _new_invoice(client, headers)
    assert (await _send(client, headers, invoice["id"], ASK)).status_code == 200
    reminder = (await _invoice_reminders(client, headers, invoice["id"]))[0]
    assert reminder["requires_approval"] is True

    # Đường 2: bộ quét hằng ngày — hóa đơn đã quá hạn thì sinh thêm lời nhắc "quá hạn".
    await db_session.execute(
        update(InvoiceModel)
        .where(InvoiceModel.id == uuid.UUID(invoice["id"]))
        .values(status="overdue", due_date=date.today() - timedelta(days=20))
    )
    await AutoReminderScheduler(db=db_session).run()
    overdue = (
        await db_session.scalars(
            select(ReminderModel).where(
                ReminderModel.target_id == uuid.UUID(invoice["id"]),
                ReminderModel.reminder_type == "payment_overdue",
            )
        )
    ).all()
    assert len(overdue) == 1
    assert overdue[0].created_by_rule is True
    assert overdue[0].requires_approval is True


async def test_tat_quy_tac_thi_gui_hoa_don_khong_dat_loi_nhac(client: AsyncClient) -> None:
    """Freelancer đã tắt "Nhắc trước khi hóa đơn tới hạn" thì không được tự gửi email nhắc khách."""
    headers = await _auth_headers(client)
    await _rule(client, headers, is_enabled=False)
    invoice = await _new_invoice(client, headers)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "sent"
    assert resp.json()["data"]["payment_reminder"]["reason"] == "disabled"
    assert await _invoice_reminders(client, headers, invoice["id"]) == []


async def test_han_thanh_toan_qua_gan_thi_van_gui_duoc_nhung_khong_dat_loi_nhac(
    client: AsyncClient,
) -> None:
    """Quy tắc nhắc trước hạn 3 ngày; hạn còn 3 ngày thì ngày nhắc là chính hôm nay."""
    headers = await _auth_headers(client)
    rule = await _rule(client, headers)
    assert rule["offset_days"] == 3
    invoice = await _new_invoice(client, headers, due_in_days=3)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "sent"
    info = resp.json()["data"]["payment_reminder"]
    assert info["scheduled"] is False and info["reason"] == "too_soon"
    assert await _invoice_reminders(client, headers, invoice["id"]) == []


async def test_han_vua_du_xa_thi_dat(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    invoice = await _new_invoice(client, headers, due_in_days=4)

    resp = await _send(client, headers, invoice["id"], ASK)

    assert resp.json()["data"]["payment_reminder"]["scheduled"] is True
    assert len(await _invoice_reminders(client, headers, invoice["id"])) == 1


async def test_khong_xin_dat_loi_nhac_thi_khong_dat(client: AsyncClient) -> None:
    """Client cũ gọi trần vẫn chạy y như trước."""
    headers = await _auth_headers(client)
    invoice = await _new_invoice(client, headers)

    resp = await _send(client, headers, invoice["id"], None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["payment_reminder"] is None
    assert await _invoice_reminders(client, headers, invoice["id"]) == []


async def test_kenh_email_ma_khach_chua_co_email_va_chi_ghi_nhan_da_gui_thi_khong_dat(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    await _rule(client, headers, channel="email")
    invoice = await _new_invoice(client, headers, client_email=None)

    resp = await _send(client, headers, invoice["id"], {"notify": False, **ASK})

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "sent"
    assert resp.json()["data"]["payment_reminder"]["reason"] == "no_client_email"
    assert await _invoice_reminders(client, headers, invoice["id"]) == []


async def test_kenh_chi_nhac_toi_thi_khach_khong_co_email_van_dat_duoc(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    await _rule(client, headers, channel="in_app")
    invoice = await _new_invoice(client, headers, client_email=None)

    resp = await _send(client, headers, invoice["id"], {"notify": False, **ASK})

    assert resp.json()["data"]["payment_reminder"]["scheduled"] is True
    assert (await _invoice_reminders(client, headers, invoice["id"]))[0]["channel"] == "in_app"


async def test_ghi_nhan_thu_du_thi_huy_loi_nhac(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    invoice = await _new_invoice(client, headers)
    await _send(client, headers, invoice["id"], ASK)

    full = await _pay(client, headers, invoice["id"], "100.00")

    assert full.json()["data"]["status"] == "paid"
    assert (await _invoice_reminders(client, headers, invoice["id"]))[0]["status"] == "cancelled"


async def test_thu_mot_phan_thi_giu_loi_nhac_va_doi_so_tien_trong_chu(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    invoice = await _new_invoice(client, headers)
    await _send(client, headers, invoice["id"], ASK)
    before = (await _invoice_reminders(client, headers, invoice["id"]))[0]
    assert "100 ₫" in before["message_preview"]

    partial = await _pay(client, headers, invoice["id"], "25.00")

    assert partial.json()["data"]["status"] == "partially_paid"
    after = (await _invoice_reminders(client, headers, invoice["id"]))[0]
    assert after["status"] == "pending"
    assert "75 ₫" in after["message_preview"]
    assert "100 ₫" not in after["message_preview"]


async def test_huy_hoa_don_thi_huy_loi_nhac(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    invoice = await _new_invoice(client, headers)
    await _send(client, headers, invoice["id"], ASK)

    resp = await client.post(f"/api/v1/invoices/{invoice['id']}/void", headers=headers)

    assert resp.status_code == 200, resp.text
    assert (await _invoice_reminders(client, headers, invoice["id"]))[0]["status"] == "cancelled"


async def test_thu_nhac_that_su_gui_di_mang_ten_du_an_chu_khong_phai_ma_hoa_don(
    client: AsyncClient,
) -> None:
    """Đúng thứ khách nhận khi bấm "Gửi ngay" trên lời nhắc tự đặt (kể cả đang chờ duyệt)."""
    headers = await _auth_headers(client)
    await _rule(client, headers, channel="email")
    invoice = await _new_invoice(client, headers)
    await _send(client, headers, invoice["id"], ASK)
    reminder = (await _invoice_reminders(client, headers, invoice["id"]))[0]

    with patch(SEND_REMINDER_EMAIL, new=AsyncMock()) as send_email:
        resp = await client.post(f"/api/v1/reminders/{reminder['id']}/send", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "sent"
    kwargs = send_email.await_args.kwargs
    assert kwargs["to"] == "khach@example.com"
    assert kwargs["subject"] == f"Nhắc thanh toán {invoice['invoice_number']}"
    # Tiêu đề dùng mã hóa đơn, nhưng chân thư nói về DỰ ÁN — không phải "Về dự án: INV-…".
    assert f"Về dự án: {DEAL_TITLE}." in kwargs["plain"]
    assert "Về dự án: INV-" not in kwargs["plain"]
    assert invoice["invoice_number"] in kwargs["plain"]
    assert kwargs["reply_to"]  # khách bấm Trả lời thì thư về hộp thư freelancer


async def test_quy_tac_cua_nguoi_nay_khong_anh_huong_hoa_don_cua_nguoi_kia(
    client: AsyncClient,
) -> None:
    headers_a = await _auth_headers(client)
    headers_b = await _auth_headers(client)
    await _rule(client, headers_a, is_enabled=False)
    invoice_b = await _new_invoice(client, headers_b)

    await _send(client, headers_b, invoice_b["id"], ASK)

    assert len(await _invoice_reminders(client, headers_b, invoice_b["id"])) == 1
    assert await _invoice_reminders(client, headers_a, invoice_b["id"]) == []
