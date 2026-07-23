"""Integration coverage for the mock MoMo subscription-checkout flow."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import SubscriptionModel, SubscriptionPaymentModel
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


async def test_webhook_on_expired_checkout_does_not_upgrade_subscription(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plan = await _pro_plan(client, headers)
    payment = await _create_checkout(client, headers, plan["id"])

    # Backdate the checkout past its TTL, as if it had been sitting unpaid.
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

    cancel_resp = await client.post("/api/v1/subscriptions/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    body = cancel_resp.json()["data"]
    assert body["cancel_at_period_end"] is True
    assert body["status"] == "active"  # access continues until period end
    assert body["plan_slug"] == "pro"

    # Already scheduled — cancelling again is rejected, not a silent no-op.
    second_cancel = await client.post("/api/v1/subscriptions/cancel", headers=headers)
    assert second_cancel.status_code == 400


async def test_cancel_subscription_on_free_plan_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)

    cancel_resp = await client.post("/api/v1/subscriptions/cancel", headers=headers)
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
    await client.post("/api/v1/subscriptions/cancel", headers=headers)

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
