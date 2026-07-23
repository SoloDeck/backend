import json
import uuid
from decimal import Decimal

import httpx
import pytest

from src.integrations.momo.client import MockMomoClient, MomoClient, PaymentGatewayError


def _momo_client(transport: httpx.MockTransport) -> MomoClient:
    return MomoClient(
        partner_code="MOMO",
        access_key="access-key",
        secret_key="secret-key",
        partner_name="SoloDesk",
        store_id="SoloDeskStore",
        endpoint="https://test-payment.momo.vn/v2/gateway/api/create",
        request_type="captureWallet",
        lang="vi",
        redirect_url="",
        timeout_seconds=5.0,
        transport=transport,
    )


async def test_create_payment_returns_success_shape() -> None:
    client = MockMomoClient()
    order_id = str(uuid.uuid4())

    result = await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert result.pay_url and order_id in result.pay_url
    assert result.deeplink and order_id in result.deeplink
    assert result.qr_code_url and order_id in result.qr_code_url
    assert result.raw["resultCode"] == 0
    assert result.raw["signature"]


def test_sign_ipn_round_trips_through_verify() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)

    assert client.verify_callback_signature(payload) is True


def test_verify_rejects_tampered_payload() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)

    payload["amount"] = payload["amount"] + 1

    assert client.verify_callback_signature(payload) is False


def test_verify_rejects_missing_fields() -> None:
    client = MockMomoClient()

    assert client.verify_callback_signature({"orderId": "x"}) is False


def test_parse_callback_success() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(order_id="order-1", amount=100000, trans_id=999)

    result = client.parse_callback(payload)

    assert result.order_id == "order-1"
    assert result.provider_reference == "999"
    assert result.success is True


def test_parse_callback_failure() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(
        order_id="order-1", amount=100000, result_code=1, message="Payment failed"
    )

    result = client.parse_callback(payload)

    assert result.success is False
    assert result.message == "Payment failed"


def test_build_ack_response_shape() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(order_id="order-1", amount=100000)
    result = client.parse_callback(payload)

    ack = client.build_ack_response(result)

    assert ack["orderId"] == "order-1"
    assert ack["resultCode"] == 0


async def test_real_client_create_payment_returns_gateway_response() -> None:
    order_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.read())
        assert sent["orderId"] == order_id
        assert sent["amount"] == 199000
        return httpx.Response(
            200,
            json={
                "partnerCode": "MOMO",
                "orderId": order_id,
                "requestId": sent["requestId"],
                "resultCode": 0,
                "message": "Success",
                "payUrl": f"https://test-payment.momo.vn/pay/{order_id}",
                "deeplink": f"momo://app?orderId={order_id}",
                "qrCodeUrl": f"https://test-payment.momo.vn/qr/{order_id}",
            },
        )

    client = _momo_client(httpx.MockTransport(handler))

    result = await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert result.pay_url and order_id in result.pay_url
    assert result.deeplink and order_id in result.deeplink
    assert result.qr_code_url and order_id in result.qr_code_url
    assert result.raw["resultCode"] == 0


async def test_real_client_raises_when_momo_rejects_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resultCode": 99, "message": "Invalid signature"})

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


async def test_real_client_raises_on_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


def test_real_client_shares_signing_logic_with_mock() -> None:
    """MomoClient uses the same IPN verify/parse/ack logic as MockMomoClient."""
    client = MomoClient(
        partner_code="MOMO",
        access_key="access-key",
        secret_key="secret-key",
        partner_name="SoloDesk",
        store_id="SoloDeskStore",
        endpoint="https://test-payment.momo.vn/v2/gateway/api/create",
        request_type="captureWallet",
        lang="vi",
        redirect_url="",
        timeout_seconds=5.0,
    )
    payload = client.sign_ipn(order_id="order-1", amount=100000)

    assert client.verify_callback_signature(payload) is True
    assert client.parse_callback(payload).success is True
