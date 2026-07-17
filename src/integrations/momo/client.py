"""Mock MoMo AIOv2 client.

Not wired to MoMo's real servers — there is no merchant account behind this.
Request/response/IPN shapes mirror MoMo's actual documented AIOv2 contract
(field names, HMAC-SHA256 signing over their raw-signature string format) so
this is a genuine sign/verify round trip, not a stub, and swapping in a real
MoMo SDK client later only touches this file.
"""

import hashlib
import hmac
import time
import uuid
from decimal import Decimal
from typing import Any

from src.modules.subscriptions.application.payment_gateway import (
    CallbackResult,
    CreatePaymentResult,
)

# Dev-only mock credentials — never real, this integration never calls momo.vn.
_PARTNER_CODE = "MOMO_MOCK"
_ACCESS_KEY = "mock-momo-access-key"
_SECRET_KEY = "mock-momo-secret-key-dev-only"
_REQUEST_TYPE = "captureWallet"
_MOCK_BASE_URL = "https://mock-payment.solodesk.dev/momo"


def _sign(raw_signature: str) -> str:
    return hmac.new(_SECRET_KEY.encode(), raw_signature.encode(), hashlib.sha256).hexdigest()


def _ipn_raw_signature(payload: dict[str, Any]) -> str:
    """MoMo's documented IPN raw-signature field order (alphabetical)."""
    return (
        f"accessKey={_ACCESS_KEY}&amount={payload['amount']}"
        f"&extraData={payload.get('extraData', '')}&message={payload['message']}"
        f"&orderId={payload['orderId']}&orderInfo={payload['orderInfo']}"
        f"&orderType={payload['orderType']}&partnerCode={payload['partnerCode']}"
        f"&payType={payload['payType']}&requestId={payload['requestId']}"
        f"&responseTime={payload['responseTime']}&resultCode={payload['resultCode']}"
        f"&transId={payload['transId']}"
    )


class MockMomoClient:
    """Implements the subscriptions module's PaymentGateway protocol."""

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
            f"accessKey={_ACCESS_KEY}&amount={amount_int}&extraData="
            f"&ipnUrl={notify_url}&orderId={order_id}&orderInfo={order_info}"
            f"&partnerCode={_PARTNER_CODE}&redirectUrl={notify_url}"
            f"&requestId={request_id}&requestType={_REQUEST_TYPE}"
        )
        pay_url = f"{_MOCK_BASE_URL}/pay/{order_id}"
        deeplink = f"momo://mock?orderId={order_id}"
        qr_code_url = f"{_MOCK_BASE_URL}/qr/{order_id}"
        raw = {
            "partnerCode": _PARTNER_CODE,
            "orderId": order_id,
            "requestId": request_id,
            "amount": amount_int,
            "responseTime": int(time.time() * 1000),
            "message": "Success",
            "resultCode": 0,
            "payUrl": pay_url,
            "deeplink": deeplink,
            "qrCodeUrl": qr_code_url,
            "signature": _sign(raw_signature),
        }
        return CreatePaymentResult(pay_url=pay_url, deeplink=deeplink, qr_code_url=qr_code_url, raw=raw)

    def verify_callback_signature(self, payload: dict[str, Any]) -> bool:
        try:
            expected = _sign(_ipn_raw_signature(payload))
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
            "partnerCode": _PARTNER_CODE,
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
            "partnerCode": _PARTNER_CODE,
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
        payload["signature"] = _sign(_ipn_raw_signature(payload))
        return payload
