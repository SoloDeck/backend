"""Integration coverage for invoice operation routes added in Phase 6."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers, _create_client

# `/send` giờ GỬI EMAIL THẬT rồi mới đánh dấu đã gửi (trước đây chỉ đổi trạng thái). Mock
# lớp SMTP chứ không dùng `notify=false`: như vậy test vẫn đi qua đường dựng thư thật trên
# PostgreSQL thật — chỗ mà unit test (mock repo) không với tới được.
SEND_EMAIL = "src.shared.email.smtp.send_email"


async def _create_deal(http: AsyncClient, headers: dict, client_id: str) -> dict:
    resp = await http.post(
        "/api/v1/deals",
        json={
            "client_id": client_id,
            "title": f"Deal {uuid.uuid4().hex[:6]}",
            "estimated_value": "1000",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _create_invoice(http: AsyncClient, headers: dict) -> dict:
    client_obj = await _create_client(http, headers)
    deal = await _create_deal(http, headers, client_obj["id"])
    resp = await http.post(
        "/api/v1/invoices",
        json={
            "client_id": client_obj["id"],
            "deal_id": deal["id"],
            "subtotal": str(Decimal("100.00")),
            "tax_rate": "0",
            "due_date": date(2026, 1, 31).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_invoice_send_payment_and_payment_list(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    invoice = await _create_invoice(client, headers)

    with patch(SEND_EMAIL, new=AsyncMock()) as send_email:
        send_resp = await client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=headers)
    assert send_resp.status_code == 200, send_resp.text
    assert send_resp.json()["data"]["status"] == "sent"
    # Thư phải thật sự được gửi đi, không chỉ đổi trạng thái.
    send_email.assert_awaited_once()

    payment_resp = await client.post(
        f"/api/v1/invoices/{invoice['id']}/payments",
        json={
            "amount": "25.00",
            "payment_date": date(2026, 1, 1).isoformat(),
            "payment_method": "other",
        },
        headers=headers,
    )
    assert payment_resp.status_code == 201
    assert payment_resp.json()["data"]["status"] == "partially_paid"

    list_resp = await client.get(f"/api/v1/invoices/{invoice['id']}/payments", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1


async def test_public_invoice_view_via_share_token(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    invoice = await _create_invoice(client, headers)

    # Send invoice to generate share_token
    with patch(SEND_EMAIL, new=AsyncMock()):
        send_resp = await client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=headers)
    assert send_resp.status_code == 200, send_resp.text
    share_token = send_resp.json()["data"].get("share_token")
    assert share_token is not None, "send() must generate a share_token"

    # Public view — no auth
    public_resp = await client.get(f"/api/v1/invoices/public/{share_token}")
    assert public_resp.status_code == 200
    assert public_resp.json()["data"]["id"] == invoice["id"]

    # Invalid token → 404
    bad_resp = await client.get("/api/v1/invoices/public/invalid_token_xyz")
    assert bad_resp.status_code == 404
