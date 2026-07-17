"""Integration coverage for the mock MoMo subscription-checkout flow."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.seeders.plans import PlansSeeder
from src.integrations.momo.client import MockMomoClient
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
