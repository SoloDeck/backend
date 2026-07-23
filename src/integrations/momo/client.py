"""MoMo AIOv2 client — https://developers.momo.vn/v2/#/docs/aiov2

`MomoClient` calls MoMo's real sandbox endpoint (test-payment.momo.vn) using
whatever partner/access/secret keys are configured in Settings — MoMo's public
sandbox test-merchant credentials by default. `MockMomoClient` stays fully
offline (no network) and is used by tests and `scripts/simulate_payment_callback.py`.

Both share the same documented request/IPN signing algorithm (HMAC-SHA256 over
MoMo's raw-signature string format) via `_MomoSignedClient`.
"""

import hashlib
import hmac
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx

from src.modules.subscriptions.application.payment_gateway import (
    CallbackResult,
    CreatePaymentResult,
)
from src.shared.exceptions.domain import DomainError


class PaymentGatewayError(DomainError):
    """The provider rejected the request or could not be reached."""

    def __init__(self, message: str = "Payment provider request failed") -> None:
        super().__init__(message)


class _MomoSignedClient:
    """Shared MoMo AIOv2 signing/verification logic (IPN + create-payment request).

    Subclasses provide the partner/access/secret keys; the raw-signature string
    formats below are MoMo's documented field orders and must not be reordered.
    """

    partner_code: str
    access_key: str
    secret_key: str

    def _sign(self, raw_signature: str) -> str:
        return hmac.new(
            self.secret_key.encode(), raw_signature.encode(), hashlib.sha256
        ).hexdigest()

    def _ipn_raw_signature(self, payload: dict[str, Any]) -> str:
        """MoMo's documented IPN raw-signature field order (alphabetical)."""
        return (
            f"accessKey={self.access_key}&amount={payload['amount']}"
            f"&extraData={payload.get('extraData', '')}&message={payload['message']}"
            f"&orderId={payload['orderId']}&orderInfo={payload['orderInfo']}"
            f"&orderType={payload['orderType']}&partnerCode={payload['partnerCode']}"
            f"&payType={payload['payType']}&requestId={payload['requestId']}"
            f"&responseTime={payload['responseTime']}&resultCode={payload['resultCode']}"
            f"&transId={payload['transId']}"
        )

    def verify_callback_signature(self, payload: dict[str, Any]) -> bool:
        try:
            expected = self._sign(self._ipn_raw_signature(payload))
        except KeyError:
            return False
        return hmac.compare_digest(expected, str(payload.get("signature", "")))

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult:
        trans_id = payload.get("transId")
        return CallbackResult(
            order_id=payload["orderId"],
            provider_reference=str(trans_id) if trans_id is not None else None,
            success=payload.get("resultCode") == 0,
            message=str(payload.get("message", "")),
        )

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        return {
            "partnerCode": self.partner_code,
            "orderId": result.order_id,
            "resultCode": 0,
            "message": "Confirm Success",
        }

    def sign_ipn(
        self,
        *,
        order_id: str,
        amount: Decimal | int,
        request_id: str | None = None,
        order_info: str = "SoloDesk plan upgrade",
        result_code: int = 0,
        message: str = "Success",
        trans_id: int | None = None,
        order_type: str = "momo_wallet",
        pay_type: str = "qr",
    ) -> dict[str, Any]:
        """Build a validly-signed IPN payload — used by tests and the dev simulate script."""
        payload = {
            "partnerCode": self.partner_code,
            "orderId": order_id,
            "requestId": request_id or str(uuid.uuid4()),
            "amount": int(amount),
            "orderInfo": order_info,
            "orderType": order_type,
            "transId": trans_id if trans_id is not None else int(time.time()),
            "resultCode": result_code,
            "message": message,
            "payType": pay_type,
            "responseTime": int(time.time() * 1000),
            "extraData": "",
        }
        payload["signature"] = self._sign(self._ipn_raw_signature(payload))
        return payload


class MomoClient(_MomoSignedClient):
    """Real MoMo AIOv2 client — calls MoMo's sandbox `/v2/gateway/api/create` endpoint.

    Implements the subscriptions module's `PaymentGateway` protocol.
    """

    def __init__(
        self,
        *,
        partner_code: str,
        access_key: str,
        secret_key: str,
        partner_name: str,
        store_id: str,
        endpoint: str,
        request_type: str,
        lang: str,
        redirect_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.partner_code = partner_code
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_name = partner_name
        self.store_id = store_id
        self.endpoint = endpoint
        self.request_type = request_type
        self.lang = lang
        self.redirect_url = redirect_url
        self.timeout_seconds = timeout_seconds
        # Test-only seam for injecting an `httpx.MockTransport` — None means
        # "use httpx's real network transport" (production behavior).
        self._transport = transport

    async def create_payment(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: str,
        order_info: str,
        notify_url: str,
    ) -> CreatePaymentResult:
        request_id = str(uuid.uuid4())
        amount_int = int(amount)  # MoMo amounts are whole VND, no decimals
        redirect_url = self.redirect_url or notify_url
        raw_signature = (
            f"accessKey={self.access_key}&amount={amount_int}&extraData="
            f"&ipnUrl={notify_url}&orderId={order_id}&orderInfo={order_info}"
            f"&partnerCode={self.partner_code}&redirectUrl={redirect_url}"
            f"&requestId={request_id}&requestType={self.request_type}"
        )
        request_body = {
            "partnerCode": self.partner_code,
            "partnerName": self.partner_name,
            "storeId": self.store_id,
            "requestId": request_id,
            "amount": amount_int,
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": redirect_url,
            "ipnUrl": notify_url,
            "lang": self.lang,
            "extraData": "",
            "requestType": self.request_type,
            "signature": self._sign(raw_signature),
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as http_client:
                response = await http_client.post(self.endpoint, json=request_body)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"Could not reach MoMo: {exc}") from exc

        if data.get("resultCode") != 0:
            raise PaymentGatewayError(
                f"MoMo rejected the payment request: {data.get('message', 'unknown error')}"
            )

        return CreatePaymentResult(
            pay_url=data.get("payUrl"),
            deeplink=data.get("deeplink"),
            qr_code_url=data.get("qrCodeUrl"),
            raw=data,
        )


# Dev-only mock credentials — never real, this integration never calls momo.vn.
_MOCK_PARTNER_CODE = "MOMO_MOCK"
_MOCK_ACCESS_KEY = "mock-momo-access-key"
_MOCK_SECRET_KEY = "mock-momo-secret-key-dev-only"
_MOCK_REQUEST_TYPE = "captureWallet"
_MOCK_BASE_URL = "https://mock-payment.solodesk.dev/momo"


class MockMomoClient(_MomoSignedClient):
    """Fully offline stand-in for `MomoClient` — used by tests and local dev.

    Never calls momo.vn. Request/response/IPN shapes mirror MoMo's actual
    documented AIOv2 contract so signature round-tripping is genuine.
    """

    partner_code = _MOCK_PARTNER_CODE
    access_key = _MOCK_ACCESS_KEY
    secret_key = _MOCK_SECRET_KEY

    async def create_payment(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: str,
        order_info: str,
        notify_url: str,
    ) -> CreatePaymentResult:
        request_id = str(uuid.uuid4())
        amount_int = int(amount)  # MoMo amounts are whole VND, no decimals
        raw_signature = (
            f"accessKey={self.access_key}&amount={amount_int}&extraData="
            f"&ipnUrl={notify_url}&orderId={order_id}&orderInfo={order_info}"
            f"&partnerCode={self.partner_code}&redirectUrl={notify_url}"
            f"&requestId={request_id}&requestType={_MOCK_REQUEST_TYPE}"
        )
        pay_url = f"{_MOCK_BASE_URL}/pay/{order_id}"
        deeplink = f"momo://mock?orderId={order_id}"
        qr_code_url = f"{_MOCK_BASE_URL}/qr/{order_id}"
        raw = {
            "partnerCode": self.partner_code,
            "orderId": order_id,
            "requestId": request_id,
            "amount": amount_int,
            "responseTime": int(time.time() * 1000),
            "message": "Success",
            "resultCode": 0,
            "payUrl": pay_url,
            "deeplink": deeplink,
            "qrCodeUrl": qr_code_url,
            "signature": self._sign(raw_signature),
        }
        return CreatePaymentResult(
            pay_url=pay_url, deeplink=deeplink, qr_code_url=qr_code_url, raw=raw
        )
