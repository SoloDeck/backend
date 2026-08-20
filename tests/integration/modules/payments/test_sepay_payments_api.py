"""Integration coverage for the SePay bank-reconciliation checkout flow.

What only a real database and a real HTTP round trip can prove:

- `provider="sepay"` survives the request schema, the service dispatch table AND the
  `payment_provider` PostgreSQL ENUM (migration c3d4e5f6a7b8).
- The `order_code` column exists, is populated at checkout, and a webhook carrying only
  that short code in a transfer memo finds its way back to the right payment row —
  there is no UUID anywhere in a SePay callback.
- The webhook answers with HTTP 200 + `{"success": true}`, which is the only response
  SePay accepts. The shared `/{provider}` route returns 202 + an ApiResponse envelope
  for every other provider, so this is a genuine branch that only a request test covers.
"""

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import SubscriptionPaymentModel
from src.infrastructure.database.seeders.plans import PlansSeeder
from src.integrations.sepay.client import MockSePayClient
from tests.integration.modules.clients.test_clients_api import _auth_headers

_WEBHOOK = "/api/v1/payments/webhooks/sepay"


async def _pro_plan(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    assert resp.status_code == 200
    return next(p for p in resp.json()["data"] if p["slug"] == "pro")


async def _create_checkout(client: AsyncClient, headers: dict, plan_id: str) -> dict:
    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plan_id, "provider": "sepay"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _order_code(db_session: AsyncSession, payment_id: str) -> str:
    row = await db_session.get(SubscriptionPaymentModel, payment_id)
    assert row is not None
    return row.order_code


async def test_checkout_then_webhook_upgrades_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])
    assert payment["status"] == "pending"
    assert payment["payment_link"]["url"]

    sepay = MockSePayClient()
    code = await _order_code(db_session, payment["id"])
    body = sepay.build_webhook_payload(order_code=code, amount=int(float(plan["price_monthly"])))

    resp = await client.post(_WEBHOOK, json=body, headers=sepay.auth_headers())

    # SePay CHỈ chấp nhận 200/201 + {"success": true} — 202 làm nó gửi lại mãi.
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True}

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"


async def test_checkout_persists_sepay_provider_and_an_order_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Thiếu migration enum thì chính câu INSERT này chết; thiếu cột order_code cũng vậy."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])

    assert payment["provider"] == "sepay"
    code = await _order_code(db_session, payment["id"])
    assert code and code.startswith("SD")


async def test_qr_url_carries_the_order_code(client: AsyncClient, db_session: AsyncSession) -> None:
    """Mã đơn phải nằm trong `des` của URL QR, nếu không tiền vào sẽ không khớp đơn nào."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])
    code = await _order_code(db_session, payment["id"])

    assert f"des={code}" in payment["payment_link"]["url"]


async def test_webhook_without_api_key_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Không có header xác thực thì bất kỳ ai POST đúng hình dạng JSON cũng nâng được gói."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    code = await _order_code(db_session, payment["id"])
    body = MockSePayClient().build_webhook_payload(
        order_code=code, amount=int(float(plan["price_monthly"]))
    )

    resp = await client.post(_WEBHOOK, json=body)

    assert resp.status_code >= 400
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_webhook_with_wrong_api_key_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    code = await _order_code(db_session, payment["id"])
    body = MockSePayClient().build_webhook_payload(
        order_code=code, amount=int(float(plan["price_monthly"]))
    )

    resp = await client.post(_WEBHOOK, json=body, headers={"Authorization": "Apikey wrong"})

    assert resp.status_code >= 400
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_webhook_replay_is_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    sepay = MockSePayClient()
    code = await _order_code(db_session, payment["id"])
    body = sepay.build_webhook_payload(order_code=code, amount=int(float(plan["price_monthly"])))

    first = await client.post(_WEBHOOK, json=body, headers=sepay.auth_headers())
    replay = await client.post(_WEBHOOK, json=body, headers=sepay.auth_headers())

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == {"success": True}


async def test_amount_mismatch_does_not_activate_the_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Đúng mã đơn nhưng chuyển thiếu tiền: KHÔNG kích hoạt, đánh dấu thất bại."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    sepay = MockSePayClient()
    code = await _order_code(db_session, payment["id"])

    resp = await client.post(
        _WEBHOOK,
        json=sepay.build_webhook_payload(order_code=code, amount=1000),
        headers=sepay.auth_headers(),
    )

    assert resp.status_code == 200
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"
    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.json()["data"]["status"] == "failed"


async def test_outgoing_transfer_never_activates_a_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Một khoản CHUYỂN ĐI trùng mã và trùng số tiền vẫn không được tính là thanh toán."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    sepay = MockSePayClient()
    code = await _order_code(db_session, payment["id"])

    resp = await client.post(
        _WEBHOOK,
        json=sepay.build_webhook_payload(
            order_code=code, amount=int(float(plan["price_monthly"])), transfer_type="out"
        ),
        headers=sepay.auth_headers(),
    )

    assert resp.status_code == 200
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_transfer_with_unknown_order_code_is_not_a_500(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Khách chuyển nhầm hoặc gõ sai mã — tiền vào thật nhưng không thuộc đơn nào."""
    await PlansSeeder(db_session).run()
    sepay = MockSePayClient()

    resp = await client.post(
        _WEBHOOK,
        json=sepay.build_webhook_payload(order_code="SDZZZZZZZZ", amount=199000),
        headers=sepay.auth_headers(),
    )

    assert resp.status_code == 404


async def test_webhook_falls_back_to_content_when_code_field_is_null(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Quy tắc tách mã ở dashboard chưa cấu hình → `code: null`, mã chỉ còn trong `content`."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])
    sepay = MockSePayClient()
    code = await _order_code(db_session, payment["id"])
    body = sepay.build_webhook_payload(
        order_code=code,
        amount=int(float(plan["price_monthly"])),
        include_code_field=False,
    )
    assert body["code"] is None

    resp = await client.post(_WEBHOOK, json=body, headers=sepay.auth_headers())

    assert resp.status_code == 200
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"


async def test_checkout_against_free_plan_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plans_resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    free_plan = next(p for p in plans_resp.json()["data"] if Decimal(p["price_monthly"]) == 0)

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": free_plan["id"], "provider": "sepay"},
        headers=headers,
    )

    assert resp.status_code == 400


async def test_momo_webhook_still_returns_the_202_envelope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Chốt rằng nhánh riêng của SePay KHÔNG đổi hình dạng phản hồi của hai cổng đang chạy.

    `build_ack_response` lần đầu tiên được dùng tới là vì SePay; MoMo/ZaloPay phải giữ
    nguyên 202 + envelope `ApiResponse` như trước.
    """
    from src.integrations.momo.client import MockMomoClient

    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plan["id"], "provider": "momo"},
        headers=headers,
    )
    payment = resp.json()["data"]

    webhook = await client.post(
        "/api/v1/payments/webhooks/momo",
        json=MockMomoClient().sign_ipn(
            order_id=payment["id"], amount=int(float(plan["price_monthly"]))
        ),
    )

    assert webhook.status_code == 202
    assert webhook.json()["data"]["accepted"] is True
