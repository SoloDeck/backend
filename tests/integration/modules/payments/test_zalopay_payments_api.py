"""Integration coverage for the ZaloPay subscription-checkout flow.

Sibling of `test_payments_api.py` (the MoMo flow). What is worth exercising here and
not in the unit suite is everything the adapter alone cannot prove:

- `provider="zalopay"` survives the request schema, the service dispatch table, AND the
  `payment_provider` PostgreSQL ENUM. That last one only exists in a real database, so
  a missing `ALTER TYPE ... ADD VALUE` migration fails HERE and nowhere else.
- The `yymmdd_<hex>` app_trans_id makes the round trip back to the right payment row.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import SubscriptionPaymentModel
from src.infrastructure.database.seeders.plans import PlansSeeder
from src.integrations.zalopay.client import MockZaloPayClient
from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _pro_plan(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    assert resp.status_code == 200
    return next(p for p in resp.json()["data"] if p["slug"] == "pro")


async def _create_checkout(client: AsyncClient, headers: dict, plan_id: str) -> dict:
    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plan_id, "provider": "zalopay"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _callback(payment_id: str, amount: float) -> dict:
    return MockZaloPayClient().sign_callback(order_id=payment_id, amount=int(amount))


async def test_checkout_then_callback_upgrades_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])
    assert payment["status"] == "pending"
    assert payment["payment_link"]["url"]

    resp = await client.post(
        "/api/v1/payments/webhooks/zalopay",
        json=_callback(payment["id"], float(plan["price_monthly"])),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["data"]["accepted"] is True
    # `event_id` cho ZaloPay nằm trong chuỗi JSON `data`, không phải ở cấp cao nhất —
    # đọc kiểu MoMo thì cột này rỗng trên mọi log webhook ZaloPay.
    assert resp.json()["data"]["event_id"].startswith(datetime.now(UTC).strftime("%y%m")[:2])

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"


async def test_checkout_persists_zalopay_as_provider(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cột `provider` là ENUM `payment_provider` của PostgreSQL, không phải text.

    Thiếu migration thêm 'zalopay' vào enum, chính câu INSERT này chết với
    `invalid input value for enum payment_provider` — sau khi đã gọi ZaloPay xong xuôi.
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])

    assert payment["provider"] == "zalopay"


async def test_callback_replay_is_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    payload = _callback(payment["id"], float(plan["price_monthly"]))

    first = await client.post("/api/v1/payments/webhooks/zalopay", json=payload)
    replay = await client.post("/api/v1/payments/webhooks/zalopay", json=payload)

    assert first.status_code == 202
    assert replay.status_code == 202


async def test_callback_with_tampered_mac_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    payload = _callback(payment["id"], float(plan["price_monthly"]))
    payload["mac"] = "0" * 64

    resp = await client.post("/api/v1/payments/webhooks/zalopay", json=payload)

    assert resp.status_code >= 400
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_callback_amount_mismatch_does_not_activate_the_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Chữ ký hợp lệ nhưng số tiền lệch: KHÔNG kích hoạt, đánh dấu thất bại, chờ người xử.

    MAC phủ cả `amount` nên đây không phải lỗ hổng bảo mật — nó là chốt chặn cho cấu hình
    sai hoặc thu thiếu. Kích hoạt trong ca này là biếu không cả gói dịch vụ.
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    resp = await client.post(
        "/api/v1/payments/webhooks/zalopay", json=_callback(payment["id"], 1000)
    )

    assert resp.status_code == 202
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"
    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.json()["data"]["status"] == "failed"


async def test_successful_callback_after_expiry_still_upgrades(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tiền là THẬT — ZaloPay chỉ gọi callback khi đã thu được.

    Từ chối kích hoạt vì intent quá hạn là lấy tiền mà không giao hàng, và ta không có
    đường hoàn tiền tự động.
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    await db_session.execute(
        update(SubscriptionPaymentModel)
        .where(SubscriptionPaymentModel.id == payment["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    await db_session.commit()

    resp = await client.post(
        "/api/v1/payments/webhooks/zalopay",
        json=_callback(payment["id"], float(plan["price_monthly"])),
    )

    assert resp.status_code == 202
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"


async def test_callback_for_unknown_order_is_not_a_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    unknown = "00000000-0000-4000-8000-000000000000"

    resp = await client.post("/api/v1/payments/webhooks/zalopay", json=_callback(unknown, 199000))

    assert resp.status_code == 404


async def test_unsupported_provider_is_rejected(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/payments/webhooks/vnpay", json={"data": "{}", "mac": "x"})

    assert resp.status_code >= 400


async def test_zalopay_result_landing_page_is_get_reachable(client: AsyncClient) -> None:
    """ZaloPay báo thành công bằng `status=1` (MoMo dùng `resultCode=0`)."""
    ok = await client.get("/api/v1/payments/webhooks/zalopay/result", params={"status": "1"})
    cancelled = await client.get("/api/v1/payments/webhooks/zalopay/result", params={"status": "0"})

    assert ok.status_code == 200
    assert "Thanh toán thành công" in ok.text
    assert cancelled.status_code == 200
    assert "Đã đóng phiên thanh toán" in cancelled.text


async def test_checkout_with_return_url_uses_it_as_redirect_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={
            "plan_id": plan["id"],
            "provider": "zalopay",
            "return_url": "https://app.solodesk.space/billing/done",
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    row = await db_session.get(SubscriptionPaymentModel, resp.json()["data"]["id"])
    assert row.raw_create_response["return_code"] == 1


async def test_checkout_against_free_plan_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plans_resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    free_plan = next(p for p in plans_resp.json()["data"] if Decimal(p["price_monthly"]) == 0)

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": free_plan["id"], "provider": "zalopay"},
        headers=headers,
    )

    assert resp.status_code == 400
