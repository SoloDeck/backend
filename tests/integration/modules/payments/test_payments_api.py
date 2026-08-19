"""Integration coverage for the mock MoMo subscription-checkout flow."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    PlanModel,
    SubscriptionModel,
    SubscriptionPaymentModel,
)
from src.infrastructure.database.seeders.plans import PlansSeeder
from src.integrations.momo.client import MockMomoClient
from src.modules.subscriptions.application.service import SubscriptionsService
from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _pro_plan(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    assert resp.status_code == 200
    return next(p for p in resp.json()["data"] if p["slug"] == "pro")


async def _create_checkout(client: AsyncClient, headers: dict, plan_id: str) -> dict:
    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plan_id, "provider": "momo"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_checkout_then_webhook_upgrades_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    payment = await _create_checkout(client, headers, plan["id"])
    assert payment["status"] == "pending"
    assert payment["payment_link"]["url"]

    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "pending"

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    webhook_resp = await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    assert webhook_resp.status_code == 202
    assert webhook_resp.json()["data"]["accepted"] is True

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"

    # Replaying the same (already-processed) callback is a no-op, not an error.
    replay_resp = await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    assert replay_resp.status_code == 202


async def test_webhook_rejects_tampered_signature(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    ipn_payload["signature"] = "tampered"

    resp = await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    assert resp.status_code == 400


async def test_webhook_success_after_expiry_still_upgrades_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Trả tiền thành công mà IPN tới muộn thì vẫn phải lên gói.

    Trước đây luồng này trả `expired` và giữ nguyên gói free — tức người dùng đã trả tiền
    mà không nhận được gì, trong khi hệ thống vẫn ack "Confirm Success" cho MoMo. Không có
    đường hoàn tiền tự động, nên phải tôn trọng khoản đã thu.  #Huynh
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    # Backdate the checkout past its TTL, as if the IPN had been delayed.
    await db_session.execute(
        update(SubscriptionPaymentModel)
        .where(SubscriptionPaymentModel.id == payment["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    webhook_resp = await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    assert webhook_resp.status_code == 202

    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.json()["data"]["status"] == "succeeded"

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == plan["slug"]


async def test_webhook_failure_after_expiry_leaves_subscription_on_free(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Callback THẤT BẠI đến muộn thì đóng intent lại — không có khoản thu nào để tôn trọng."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    await db_session.execute(
        update(SubscriptionPaymentModel)
        .where(SubscriptionPaymentModel.id == payment["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"],
        amount=int(float(plan["price_monthly"])),
        result_code=1,
        message="Payment failed",
    )
    webhook_resp = await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    assert webhook_resp.status_code == 202

    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.json()["data"]["status"] == "expired"

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_polling_a_stale_pending_checkout_reports_expired(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    await db_session.execute(
        update(SubscriptionPaymentModel)
        .where(SubscriptionPaymentModel.id == payment["id"])
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    status_resp = await client.get(f"/api/v1/payments/intents/{payment['id']}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "expired"


async def test_cancel_pending_payment_intent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    cancel_resp = await client.post(
        f"/api/v1/payments/intents/{payment['id']}/cancel", headers=headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["status"] == "cancelled"

    second_cancel = await client.post(
        f"/api/v1/payments/intents/{payment['id']}/cancel", headers=headers
    )
    assert second_cancel.status_code == 409


async def test_checkout_against_free_plan_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/subscriptions/plans", headers=headers)
    free_plan = next(p for p in resp.json()["data"] if p["slug"] == "free")

    checkout_resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": free_plan["id"], "provider": "momo"},
        headers=headers,
    )
    assert checkout_resp.status_code == 400


async def test_checkout_against_legacy_plan_below_momo_minimum_explains_why(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Gói giá 200đ tạo TRƯỚC bản vá vẫn nằm trong DB — bấm mua phải nói rõ vì sao hỏng.

    Gói được ghi thẳng qua ORM chứ không qua API quản trị, vì API giờ đã chặn từ đầu.
    Đây đúng là tình trạng của bản deploy: dữ liệu cũ còn đó, và tầng cổng thanh toán là
    chốt chặn cuối cùng. Câu trả về phải nói tới hạn mức, KHÔNG được đổ cho lỗi mạng như
    thông báo "Could not reach MoMo" trước đây.
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)

    legacy = PlanModel(
        name="abc",
        slug="abc",
        price_monthly=Decimal("200"),
        currency="VND",
        is_active=True,
    )
    db_session.add(legacy)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": str(legacy.id), "provider": "momo"},
        headers=headers,
    )

    assert resp.status_code == 400
    message = resp.json()["error"]["message"]
    assert "1.000" in message and "50.000.000" in message
    assert "kết nối" not in message


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
            "provider": "momo",
            "return_url": "https://app.solodesk.space/billing/result",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    payment_id = resp.json()["data"]["id"]
    row = await db_session.get(SubscriptionPaymentModel, payment_id)
    assert row.raw_create_response["redirectUrl"] == "https://app.solodesk.space/billing/result"


async def test_checkout_rejects_non_http_return_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={
            "plan_id": plan["id"],
            "provider": "momo",
            "return_url": "javascript:alert(1)",
        },
        headers=headers,
    )
    assert resp.status_code == 422


async def test_checkout_accepts_registered_deep_link_return_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)

    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={
            "plan_id": plan["id"],
            "provider": "momo",
            "return_url": "solodesk://payment-result",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    payment_id = resp.json()["data"]["id"]
    row = await db_session.get(SubscriptionPaymentModel, payment_id)
    assert row.raw_create_response["redirectUrl"] == "solodesk://payment-result"


async def test_momo_result_landing_page_is_get_reachable(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/payments/webhooks/momo/result",
        params={"resultCode": "1006"},
    )
    assert resp.status_code == 200


async def test_cancel_subscription_after_upgrade(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)

    cancel_resp = await client.post("/api/v1/subscriptions/me/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    body = cancel_resp.json()["data"]
    assert body["cancel_at_period_end"] is True
    assert body["status"] == "active"  # access continues until period end
    assert body["plan_slug"] == "pro"

    # Already scheduled — cancelling again is rejected, not a silent no-op.
    second_cancel = await client.post("/api/v1/subscriptions/me/cancel", headers=headers)
    assert second_cancel.status_code == 400


async def test_cancel_subscription_on_free_plan_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)

    cancel_resp = await client.post("/api/v1/subscriptions/me/cancel", headers=headers)
    assert cancel_resp.status_code == 400


async def test_expire_lapsed_subscriptions_downgrades_scheduled_cancellation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """End-to-end: upgrade via MoMo, schedule cancellation, let the period
    lapse, then run the Beat job that's supposed to enforce it."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)
    await client.post("/api/v1/subscriptions/me/cancel", headers=headers)

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    subscription_id = me_resp.json()["data"]["id"]

    # Backdate as if the billing period already ended.
    await db_session.execute(
        update(SubscriptionModel)
        .where(SubscriptionModel.id == subscription_id)
        .values(current_period_end=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    count = await SubscriptionsService(db=db_session).expire_lapsed_subscriptions()
    assert count == 1

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    body = me_resp.json()["data"]
    assert body["plan_slug"] == "free"
    assert body["cancel_at_period_end"] is False


async def test_expire_lapsed_subscriptions_also_expires_without_explicit_cancel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No recurring auto-charge exists — a paid period that lapses without a
    fresh checkout expires too, even if the user never called /cancel."""
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    subscription_id = me_resp.json()["data"]["id"]

    await db_session.execute(
        update(SubscriptionModel)
        .where(SubscriptionModel.id == subscription_id)
        .values(current_period_end=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    count = await SubscriptionsService(db=db_session).expire_lapsed_subscriptions()
    assert count == 1

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_expire_lapsed_subscriptions_survives_renaming_the_free_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Đổi TÊN gói Free không được làm job hạ gói ngừng hoạt động.

    Bản cũ tra gói miễn phí theo ``name == "Free"``. Admin đổi tên thành "Miễn phí" qua
    màn quản trị là `get_free_plan()` trả None, `expire_lapsed_subscriptions` lặng lẽ
    `return 0`, và người hết hạn gói trả phí GIỮ NGUYÊN quyền lợi trả phí vĩnh viễn —
    không lỗi, không log, không ai biết cho tới lúc đối soát doanh thu.

    `auth` đã sửa sang tra theo `slug` từ trước; bản ở module này bị bỏ sót.  #Huynh
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    subscription_id = me_resp.json()["data"]["id"]

    # Đúng thao tác admin làm được từ màn quản trị: đổi tên hiển thị, giữ nguyên mã.
    await db_session.execute(
        update(PlanModel).where(PlanModel.slug == "free").values(name="Miễn phí")
    )
    await db_session.execute(
        update(SubscriptionModel)
        .where(SubscriptionModel.id == subscription_id)
        .values(current_period_end=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    count = await SubscriptionsService(db=db_session).expire_lapsed_subscriptions()

    assert count == 1
    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "free"


async def test_expire_lapsed_subscriptions_leaves_current_subscriptions_alone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    ipn_payload = MockMomoClient().sign_ipn(
        order_id=payment["id"], amount=int(float(plan["price_monthly"]))
    )
    await client.post("/api/v1/payments/webhooks/momo", json=ipn_payload)

    count = await SubscriptionsService(db=db_session).expire_lapsed_subscriptions()
    assert count == 0

    me_resp = await client.get("/api/v1/subscriptions/me", headers=headers)
    assert me_resp.json()["data"]["plan_slug"] == "pro"
