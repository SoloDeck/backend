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
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog

from src.modules.subscriptions.application.payment_gateway import (
    CallbackResult,
    CreatePaymentResult,
)
from src.shared.exceptions.domain import DomainError

log = structlog.get_logger(__name__)

# Hạn mức MoMo công bố cho MỘT giao dịch:
# https://developers.momo.vn/v3/docs/payment/api/wallet/onetime/
# Đây là BẢN SAO mặc định, phục vụ `MockMomoClient` (không đi qua DI) và test dựng
# `MomoClient` trực tiếp. Đường chạy thật lấy số từ Settings — xem
# `shared/dependencies/payments.py`. Hai chỗ phải khớp nhau.
MOMO_MIN_AMOUNT_VND = 1_000
MOMO_MAX_AMOUNT_VND = 50_000_000

# MoMo giới hạn `orderInfo` 255 ký tự.
_ORDER_INFO_MAX_LENGTH = 255

# Hai ký tự phân tách của chuỗi ký — xem `_safe_order_info`.
_ORDER_INFO_UNSAFE = re.compile(r"[&=]")


class PaymentGatewayError(DomainError):
    """The provider rejected the request or could not be reached."""

    def __init__(self, message: str = "Payment provider request failed") -> None:
        super().__init__(message)


def _vnd(amount: Decimal | int) -> str:
    """Số tiền theo lối Việt: ``50000000`` → ``"50.000.000"``.

    Chuỗi này đi thẳng ra toast đỏ trước mặt người dùng, nên định dạng theo lối Việt
    chứ không để nguyên dấu phẩy kiểu Anh.
    """
    return f"{int(amount):,}".replace(",", ".")


def _read_momo_payload(response: httpx.Response) -> dict[str, Any]:
    """Thân JSON của MoMo — đọc CẢ KHI mã HTTP là 4xx/5xx.

    Bản trước gọi ``raise_for_status()`` ngay trước ``response.json()``, nên với một 400
    thì thân phản hồi — đúng chỗ MoMo ghi ``resultCode`` và ``message`` nói CHÍNH XÁC nó
    chê gì — bị vứt đi không đọc lấy một lần. Thứ còn lại cho người dùng là
    ``"Client error '400 ' for url ..."``: một câu vừa không nói được nguyên nhân, vừa
    chỉ SAI hướng (nghe như hỏng mạng, trong khi mạng hoàn toàn bình thường).

    MoMo có thể trả HTML thay vì JSON khi đi qua proxy/WAF. Không đọc được thì trả dict
    rỗng để phía gọi lùi về báo theo mã HTTP, chứ đừng ném thêm một lỗi thứ hai đè lên
    lỗi đang cần chẩn đoán.  #Huynh
    """
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _momo_rejection_message(response: httpx.Response, data: dict[str, Any]) -> str:
    """Câu báo cho người dùng khi MoMo TỪ CHỐI — khác hẳn với khi không gọi tới được.

    Ưu tiên nguyên văn ``message`` của MoMo: request gửi kèm ``lang=vi`` nên câu đó vốn
    đã là tiếng Việt, và nó chính xác hơn mọi câu đoán hộ. Kèm ``resultCode`` để còn tra
    được tài liệu.
    """
    detail = str(data.get("message") or "").strip()
    result_code = data.get("resultCode")
    if detail and result_code is not None:
        return f"MoMo từ chối yêu cầu thanh toán: {detail} (mã {result_code})."
    if detail:
        return f"MoMo từ chối yêu cầu thanh toán: {detail}."
    return (
        f"MoMo từ chối yêu cầu thanh toán (HTTP {response.status_code}) và không kèm lý "
        f"do đọc được. Bạn thử lại sau ít phút giúp mình nhé."
    )


def _is_success_code(result_code: Any) -> bool:
    """MoMo báo thành công bằng ``resultCode`` = 0. Nhận cả ``0`` lẫn ``"0"``.

    Bản trước so thẳng ``payload.get("resultCode") == 0``. JSON chuẩn của MoMo trả số
    nguyên, nhưng chỉ cần một khâu trung gian biến nó thành chuỗi (proxy, form-encoded,
    bản mock của đối tác) là phép so ra ``False`` — và **thanh toán thành công bị ghi nhận
    là THẤT BẠI**. Chữ ký vẫn khớp, vì chuỗi ký nội suy ``resultCode`` thành text ở cả hai
    phía, nên lỗi lọt qua mọi lớp kiểm mà không để lại dấu vết.

    Không parse được thì coi là thất bại: thà không kích hoạt gói còn hơn kích hoạt nhầm
    cho một callback không đọc nổi.  #Huynh
    """
    try:
        return int(str(result_code).strip()) == 0
    except (TypeError, ValueError):
        return False


def _parse_amount(amount: Any) -> Decimal | None:
    """Số tiền MoMo báo đã thu. ``None`` khi thiếu hoặc không đọc được.

    Qua ``str()`` chứ không ``Decimal(float)``: dựng Decimal từ float kéo theo sai số nhị
    phân (``Decimal(199000.0)`` không phải lúc nào cũng đúng y con số), mà đây là TIỀN.
    """
    if amount is None:
        return None
    try:
        return Decimal(str(amount).strip())
    except (TypeError, ValueError, InvalidOperation):
        return None


class _MomoSignedClient:
    """Shared MoMo AIOv2 signing/verification logic (IPN + create-payment request).

    Subclasses provide the partner/access/secret keys; the raw-signature string
    formats below are MoMo's documented field orders and must not be reordered.
    """

    partner_code: str
    access_key: str
    secret_key: str
    # Ghi ở lớp cha để `MockMomoClient` (không có `__init__`) dùng chung; `MomoClient`
    # nhận số từ Settings và ghi đè ở cấp instance.
    min_amount: int = MOMO_MIN_AMOUNT_VND
    max_amount: int = MOMO_MAX_AMOUNT_VND

    def _sign(self, raw_signature: str) -> str:
        return hmac.new(
            self.secret_key.encode(), raw_signature.encode(), hashlib.sha256
        ).hexdigest()

    def _to_whole_vnd(self, amount: Decimal, currency: str) -> int:
        """MoMo chỉ nhận VND, số nguyên, VÀ nằm trong hạn mức nó công bố.

        Hai kiểm tra đầu có sẵn: chúng chặn thứ mà ``int()`` sẽ âm thầm cắt cụt hoặc thu
        sai. Kiểm tra hạn mức là phần mới, và nó là **chốt chặn cuối trước khi rời tiến
        trình**: `AdminService` đã chặn giá gói ngay lúc ghi, nhưng DB đang chạy CÓ SẴN
        những gói tạo trước bản vá này. Một gói 200đ trong dữ liệu cũ phải chết ở ĐÂY,
        với câu nói rõ nó sai gì — chứ không được bắn lên MoMo để nhận về một cái HTTP
        400 trần rồi hiện ra trước mặt người dùng thành lỗi mạng.  #Huynh
        """
        if currency != "VND":
            raise PaymentGatewayError(
                f"MoMo chỉ thanh toán được bằng VND, gói này đang để '{currency}'. "
                f"Bạn liên hệ quản trị viên để chỉnh lại gói giúp mình nhé."
            )
        if amount != amount.to_integral_value():
            raise PaymentGatewayError(
                f"MoMo chỉ nhận số tiền chẵn (không có phần lẻ), gói này là {amount}."
            )
        value = int(amount)
        if not self.min_amount <= value <= self.max_amount:
            raise PaymentGatewayError(
                f"MoMo chỉ nhận số tiền từ {_vnd(self.min_amount)}đ đến "
                f"{_vnd(self.max_amount)}đ cho một giao dịch — gói này đang để "
                f"{_vnd(value)}đ nên không thanh toán được. Bạn liên hệ quản trị viên "
                f"để chỉnh lại giá gói giúp mình nhé."
            )
        return value

    @staticmethod
    def _safe_order_info(order_info: str) -> str:
        """``orderInfo`` đã an toàn để nội suy vào chuỗi ký.

        Chuỗi ký của MoMo có dạng ``accessKey=...&amount=...&orderInfo=<đây>&partnerCode=...``.
        Tên gói chứa ``&`` hoặc ``=`` (gói "A & B", "x=y") chèn thêm cặp khoá/giá trị giả
        vào giữa chuỗi đó. Hai phía vẫn nội suy cùng một chuỗi nên chữ ký chưa chắc lệch,
        nhưng MoMo khuyến nghị tránh ký tự đặc biệt trong ``orderInfo`` và ta không kiểm
        soát được phía họ chuẩn hoá thế nào — mà triệu chứng nếu vỡ thì lại y hệt sự cố
        đang vá: HTTP 400 trần, không nói được vì sao.

        Thay bằng khoảng trắng chứ không xoá, để tên gói còn đọc được trên app MoMo.  #Huynh
        """
        cleaned = _ORDER_INFO_UNSAFE.sub(" ", order_info).strip()
        return (cleaned or "SoloDesk plan upgrade")[:_ORDER_INFO_MAX_LENGTH]

    def _resolve_redirect_url(
        self, redirect_url: str | None, default: str | None, notify_url: str
    ) -> str:
        """Never let the browser redirect target collapse to the POST-only IPN
        notify_url — that's exactly the bug where a user cancelling on MoMo's
        checkout page gets redirected into a 405 instead of back to the app."""
        resolved = redirect_url or default
        if not resolved or resolved == notify_url:
            raise PaymentGatewayError(
                "MoMo redirect_url must be configured and must differ from "
                "notify_url (the POST-only IPN webhook)"
            )
        return resolved

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
            success=_is_success_code(payload.get("resultCode")),
            message=str(payload.get("message", "")),
            amount=_parse_amount(payload.get("amount")),
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
        min_amount: int = MOMO_MIN_AMOUNT_VND,
        max_amount: int = MOMO_MAX_AMOUNT_VND,
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
        self.min_amount = min_amount
        self.max_amount = max_amount
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
        redirect_url: str | None = None,
    ) -> CreatePaymentResult:
        request_id = str(uuid.uuid4())
        amount_int = self._to_whole_vnd(amount, currency)
        order_info = self._safe_order_info(order_info)
        redirect_url = self._resolve_redirect_url(redirect_url, self.redirect_url, notify_url)
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

        # `raise_for_status()` KHÔNG còn nằm trong khối try. Ranh giới mới:
        #   - trong try  = "không gọi tới được MoMo" (timeout, DNS, TLS, đứt kết nối)
        #   - ngoài try  = "gọi tới được, MoMo có trả lời, và câu trả lời là TỪ CHỐI"
        #
        # Gộp hai chuyện đó vào một câu chính là gốc của cả sự cố này: `HTTPStatusError`
        # là lớp con của `HTTPError`, nên một gói giá 200đ (dưới hạn mức MoMo) bị báo
        # thành lỗi mạng — và không ai nghĩ tới việc đi xem lại giá gói.  #Huynh
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as http_client:
                response = await http_client.post(self.endpoint, json=request_body)
        except httpx.HTTPError as exc:
            log.warning(
                "momo.create_payment_unreachable",
                order_id=order_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise PaymentGatewayError(
                "Không kết nối được tới MoMo lúc này. Bạn thử lại sau ít phút giúp mình nhé."
            ) from exc

        data = _read_momo_payload(response)

        # Một điều kiện cho CẢ HAI kiểu từ chối: mã HTTP 4xx/5xx (sai định dạng, quá hạn
        # mức, sai chữ ký) và HTTP 200 kèm `resultCode != 0` (từ chối nghiệp vụ). Trước
        # đây chỉ nhánh sau được xử tử tế; nhánh trước bị `raise_for_status()` nuốt mất
        # thân JSON trước khi kịp đọc.
        #
        # Dùng `_is_success_code` thay vì so `!= 0` như cũ: helper đó đã xử đúng ca MoMo
        # trả `"0"` dạng chuỗi (xem docstring của nó), và ca thiếu hẳn `resultCode` vẫn
        # ra False y như hành vi cũ.
        if response.is_error or not _is_success_code(data.get("resultCode")):
            log.warning(
                "momo.create_payment_rejected",
                order_id=order_id,
                amount=amount_int,
                status_code=response.status_code,
                result_code=data.get("resultCode"),
                momo_message=data.get("message"),
            )
            raise PaymentGatewayError(_momo_rejection_message(response, data))

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
    redirect_url = f"{_MOCK_BASE_URL}/result"

    async def create_payment(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: str,
        order_info: str,
        notify_url: str,
        redirect_url: str | None = None,
    ) -> CreatePaymentResult:
        request_id = str(uuid.uuid4())
        amount_int = self._to_whole_vnd(amount, currency)
        order_info = self._safe_order_info(order_info)
        redirect_url = self._resolve_redirect_url(redirect_url, self.redirect_url, notify_url)
        raw_signature = (
            f"accessKey={self.access_key}&amount={amount_int}&extraData="
            f"&ipnUrl={notify_url}&orderId={order_id}&orderInfo={order_info}"
            f"&partnerCode={self.partner_code}&redirectUrl={redirect_url}"
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
            "redirectUrl": redirect_url,
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
