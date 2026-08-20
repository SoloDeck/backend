"""ZaloPay Open API v2 client — https://docs.zalopay.vn/docs/specs/order-create/

`ZaloPayClient` calls ZaloPay's real sandbox endpoint (sb-openapi.zalopay.vn)
using whatever app/key credentials are configured in Settings — ZaloPay's own
published sandbox test app (2554) by default. `MockZaloPayClient` stays fully
offline (no network) and is used by tests and local dev.

Both share the documented signing algorithm (HMAC-SHA256) via `_ZaloPaySigned`.

Three things differ structurally from the MoMo adapter next door, and each one
has bitten an integration before:

1. TWO keys, not one. `key1` signs our outbound create-order request; `key2`
   verifies ZaloPay's inbound callback. Signing a callback check with key1
   silently rejects every real payment.
2. The callback body is NOT flat. ZaloPay POSTs
   ``{"data": "<a JSON *string*>", "mac": "..."}`` and the MAC covers that raw
   string verbatim — re-serialising the parsed dict changes key order/spacing
   and breaks the comparison.
3. ZaloPay only calls back on SUCCESS. There is no failure callback and no
   result-code field to read, so `parse_callback` reports success for any
   payload whose MAC verifies. See `parse_callback` for why that is safe.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog

from src.modules.subscriptions.application.payment_gateway import (
    CallbackResult,
    CreatePaymentResult,
    PaymentGatewayError,
)

log = structlog.get_logger(__name__)

__all__ = [
    "ZALOPAY_MAX_AMOUNT_VND",
    "ZALOPAY_MIN_AMOUNT_VND",
    "MockZaloPayClient",
    "PaymentGatewayError",
    "ZaloPayClient",
    "build_app_trans_id",
    "order_id_from_app_trans_id",
]

# Giờ Việt Nam. ZaloPay đối soát theo GMT+7, và `app_trans_id` BẮT BUỘC mở đầu bằng
# `yymmdd` của "ngày hôm nay" THEO GIỜ ĐÓ — không phải theo UTC.
#
# Toàn bộ entity trong repo này dùng `datetime.now(UTC)`. Từ 00:00 đến 07:00 giờ Việt,
# UTC vẫn đang ở NGÀY HÔM TRƯỚC, nên lấy ngày UTC là gửi sai tiền tố và ZaloPay từ chối
# đơn. Lỗi này chỉ xuất hiện trong 7 tiếng mỗi ngày, nên nó qua được mọi lần chạy thử
# ban ngày và chỉ chết lúc rạng sáng.
_ICT = timezone(timedelta(hours=7))

# `app_trans_id`: tối đa 40 ký tự, mở đầu bằng `yymmdd` — bảng tham số của
# https://docs.zalopay.vn/docs/specs/order-create/
#
# Ta ghép `yymmdd_` (7) + UUID dạng hex KHÔNG gạch ngang (32) = 39 ký tự, vừa khít.
# Để nguyên gạch ngang là 36 → tổng 43 → VƯỢT hạn mức. Đây chính là chỗ thiết kế hiện
# tại đâm vào ZaloPay: `SubscriptionPayment.id` (một UUID) ĐƯỢC DÙNG LUÔN làm mã đơn,
# không có cột order-id riêng để tách ra.
_APP_TRANS_ID_MAX_LENGTH = 40
_APP_TRANS_ID_DATE_LENGTH = 6

# `description` hiện trên app ZaloPay — tối đa 256 ký tự.
_DESCRIPTION_MAX_LENGTH = 256

# Khoảng tiền cho MỘT đơn. Cận dưới 1.000đ là mức ZaloPay công bố cho giao dịch trên
# app; cận trên để bằng MoMo (50tr) cho nhất quán giữa hai cổng — trần THẬT của một
# merchant là con số trong hợp đồng, không phải hằng số công khai, nên hai giá trị này
# nằm ở Settings để môi trường thật chỉnh bằng env.
ZALOPAY_MIN_AMOUNT_VND = 1_000
ZALOPAY_MAX_AMOUNT_VND = 50_000_000

# ZaloPay báo thành công bằng return_code = 1 (MoMo dùng 0 — đừng chép nhầm).
_RETURN_CODE_SUCCESS = 1

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def _vnd(amount: Decimal | int) -> str:
    """``50000000`` → ``"50.000.000"`` — định dạng cho câu báo trước mặt người dùng."""
    return f"{int(amount):,}".replace(",", ".")


def build_app_trans_id(order_id: str, *, now: datetime | None = None) -> str:
    """`order_id` của ta → `app_trans_id` hợp lệ với ZaloPay.

    Dạng ra: ``yymmdd_<32 hex>`` với ngày lấy theo giờ Việt Nam (xem `_ICT`).

    `order_id` không phải UUID vẫn dùng được (test, dữ liệu cũ): bỏ hết ký tự không
    phải chữ/số rồi cắt cho vừa 40. Chỉ cắt PHẦN ĐUÔI, không bao giờ đụng tới 7 ký tự
    tiền tố ngày — mất tiền tố là ZaloPay từ chối cả đơn.
    """
    stamp = (now or datetime.now(UTC)).astimezone(_ICT).strftime("%y%m%d")
    try:
        suffix = uuid.UUID(order_id).hex
    except (ValueError, AttributeError, TypeError):
        suffix = _NON_ALNUM.sub("", str(order_id))
    budget = _APP_TRANS_ID_MAX_LENGTH - _APP_TRANS_ID_DATE_LENGTH - 1
    return f"{stamp}_{suffix[:budget]}"


def order_id_from_app_trans_id(app_trans_id: str) -> str:
    """Đảo lại `build_app_trans_id`: bỏ tiền tố ngày, trả phần mã đơn.

    Trả về hex 32 ký tự — ``uuid.UUID(hex)`` đọc được, nên
    `SubscriptionsService.handle_payment_callback` tra ra đúng bản ghi mà không cần
    biết ZaloPay đã bọc thêm gì. Không có dấu ``_`` thì trả nguyên chuỗi.
    """
    _, separator, suffix = str(app_trans_id).partition("_")
    return suffix if separator else str(app_trans_id)


def _parse_amount(amount: Any) -> Decimal | None:
    """Số tiền ZaloPay báo đã thu. ``None`` khi thiếu hoặc không đọc được.

    Qua ``str()`` chứ không ``Decimal(float)``: dựng Decimal từ float kéo theo sai số
    nhị phân, mà đây là TIỀN.
    """
    if amount is None:
        return None
    try:
        return Decimal(str(amount).strip())
    except (TypeError, ValueError, InvalidOperation):
        return None


def _is_success_code(return_code: Any) -> bool:
    """ZaloPay báo thành công bằng ``return_code`` = 1. Nhận cả ``1`` lẫn ``"1"``.

    Cùng lý do như bên MoMo: chỉ cần một khâu trung gian (proxy, form-encoded, bản mock
    của đối tác) biến số thành chuỗi là phép so ``== 1`` ra False, và một đơn tạo THÀNH
    CÔNG bị coi là hỏng. Không đọc được thì coi là thất bại.
    """
    try:
        return int(str(return_code).strip()) == _RETURN_CODE_SUCCESS
    except (TypeError, ValueError):
        return False


def _rejection_message(data: dict[str, Any], status_code: int) -> str:
    """Câu báo khi ZaloPay TỪ CHỐI — khác hẳn với khi không gọi tới được.

    Ưu tiên nguyên văn ``sub_return_message``: nó cụ thể hơn ``return_message``
    (thường chỉ là "Giao dịch thất bại") và vốn đã là tiếng Việt.
    """
    detail = str(data.get("sub_return_message") or data.get("return_message") or "").strip()
    code = data.get("sub_return_code", data.get("return_code"))
    if detail and code is not None:
        return f"ZaloPay từ chối yêu cầu thanh toán: {detail} (mã {code})."
    if detail:
        return f"ZaloPay từ chối yêu cầu thanh toán: {detail}."
    return (
        f"ZaloPay từ chối yêu cầu thanh toán (HTTP {status_code}) và không kèm lý do "
        f"đọc được. Bạn thử lại sau ít phút giúp mình nhé."
    )


def _read_payload(response: httpx.Response) -> dict[str, Any]:
    """Thân JSON của ZaloPay — đọc CẢ KHI mã HTTP là 4xx/5xx.

    Thân phản hồi là chỗ ZaloPay ghi `return_code`/`sub_return_message`, tức là lý do
    THẬT nó chê. Gọi `raise_for_status()` trước khi đọc là vứt đúng thứ đang cần.
    """
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


class _ZaloPaySigned:
    """Phần ký/kiểm chữ ký dùng chung cho client thật và bản mock.

    Thứ tự trường trong mỗi chuỗi ký là thứ tự ZaloPay công bố — KHÔNG được đổi.
    """

    app_id: str
    key1: str
    key2: str
    app_user: str
    redirect_url: str
    # Đặt ở lớp cha để `MockZaloPayClient` (không có `__init__`) dùng chung;
    # `ZaloPayClient` nhận số từ Settings và ghi đè ở cấp instance.
    min_amount: int = ZALOPAY_MIN_AMOUNT_VND
    max_amount: int = ZALOPAY_MAX_AMOUNT_VND

    @staticmethod
    def _hmac(key: str, data: str) -> str:
        return hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()

    def _sign_create(self, body: dict[str, Any]) -> str:
        """Chuỗi ký của create-order, ký bằng **key1**.

        hmacinput = app_id|app_trans_id|app_user|amount|app_time|embed_data|item
        https://docs.zalopay.vn/docs/specs/order-create/
        """
        raw = (
            f"{body['app_id']}|{body['app_trans_id']}|{body['app_user']}|"
            f"{body['amount']}|{body['app_time']}|{body['embed_data']}|{body['item']}"
        )
        return self._hmac(self.key1, raw)

    def _sign_query(self, app_trans_id: str) -> str:
        """Chuỗi ký của query-status, ký bằng **key1**: app_id|app_trans_id|key1."""
        return self._hmac(self.key1, f"{self.app_id}|{app_trans_id}|{self.key1}")

    def _to_whole_vnd(self, amount: Decimal, currency: str) -> int:
        """ZaloPay chỉ nhận VND, số nguyên, VÀ nằm trong hạn mức.

        Chốt chặn cuối trước khi rời tiến trình. `AdminService` đã chặn giá gói lúc ghi,
        nhưng DB đang chạy CÓ SẴN những gói tạo trước bản vá đó. Một gói 200đ phải chết
        ở ĐÂY với câu nói rõ nó sai gì — chứ không bắn lên ZaloPay để nhận về một mã lỗi
        trần rồi hiện ra trước mặt người dùng thành lỗi mạng.
        """
        if currency != "VND":
            raise PaymentGatewayError(
                f"ZaloPay chỉ thanh toán được bằng VND, gói này đang để '{currency}'. "
                f"Bạn liên hệ quản trị viên để chỉnh lại gói giúp mình nhé."
            )
        if amount != amount.to_integral_value():
            raise PaymentGatewayError(
                f"ZaloPay chỉ nhận số tiền chẵn (không có phần lẻ), gói này là {amount}."
            )
        value = int(amount)
        if not self.min_amount <= value <= self.max_amount:
            raise PaymentGatewayError(
                f"ZaloPay chỉ nhận số tiền từ {_vnd(self.min_amount)}đ đến "
                f"{_vnd(self.max_amount)}đ cho một giao dịch — gói này đang để "
                f"{_vnd(value)}đ nên không thanh toán được. Bạn liên hệ quản trị viên "
                f"để chỉnh lại giá gói giúp mình nhé."
            )
        return value

    @staticmethod
    def _safe_description(order_info: str) -> str:
        cleaned = str(order_info).strip()
        return (cleaned or "SoloDesk plan upgrade")[:_DESCRIPTION_MAX_LENGTH]

    def _resolve_redirect_url(
        self, redirect_url: str | None, default: str | None, notify_url: str
    ) -> str:
        """Không bao giờ để đích redirect của trình duyệt tụt về `notify_url`.

        `notify_url` là webhook CHỈ NHẬN POST. Trỏ trình duyệt vào đó thì người dùng bấm
        huỷ trên trang ZaloPay sẽ rơi thẳng vào một trang 405 — đúng con bug đã xảy ra
        một lần với MoMo.
        """
        resolved = redirect_url or default
        if not resolved or resolved == notify_url:
            raise PaymentGatewayError(
                "ZaloPay redirect_url must be configured and must differ from "
                "notify_url (the POST-only callback webhook)"
            )
        return resolved

    def _build_create_body(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: str,
        order_info: str,
        notify_url: str,
        redirect_url: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        amount_int = self._to_whole_vnd(amount, currency)
        resolved_redirect = self._resolve_redirect_url(redirect_url, self.redirect_url, notify_url)
        # `redirecturl` nằm TRONG embed_data — ZaloPay không có tham số redirect riêng ở
        # cấp cao nhất như MoMo. Và vì embed_data được nội suy nguyên văn vào chuỗi ký,
        # chuỗi JSON này phải được sinh MỘT LẦN rồi dùng lại y hệt cho cả body lẫn chữ ký.
        embed_data = json.dumps(
            {"redirecturl": resolved_redirect}, separators=(",", ":"), ensure_ascii=False
        )
        body = {
            "app_id": self.app_id,
            "app_trans_id": build_app_trans_id(order_id, now=now),
            "app_user": self.app_user,
            "app_time": int((now or datetime.now(UTC)).timestamp() * 1000),
            "amount": amount_int,
            "item": "[]",
            "embed_data": embed_data,
            "description": self._safe_description(order_info),
            "bank_code": "",
            "callback_url": notify_url,
        }
        body["mac"] = self._sign_create(body)
        return body

    def verify_callback_signature(
        self, payload: dict[str, Any], headers: Mapping[str, str] | None = None
    ) -> bool:
        """MAC của callback, ký bằng **key2** trên chuỗi `data` NGUYÊN VĂN.

        `headers` không dùng tới: ZaloPay ký trong thân request. Tham số có mặt để khớp
        protocol `PaymentGateway` — xem docstring bên đó.


        Phải lấy đúng chuỗi ZaloPay gửi, không được parse rồi serialise lại: khoảng
        trắng và thứ tự khoá sẽ khác đi và MAC lệch — trong khi dữ liệu vẫn "đúng", nên
        triệu chứng là mọi thanh toán thật đều bị từ chối mà không rõ vì sao.
        """
        raw_data = payload.get("data")
        mac = payload.get("mac")
        if not isinstance(raw_data, str) or not isinstance(mac, str):
            return False
        return hmac.compare_digest(self._hmac(self.key2, raw_data), mac)

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult:
        """Callback đã kiểm chữ ký → `CallbackResult`.

        `success=True` cho MỌI payload qua được chữ ký, vì **ZaloPay chỉ gọi callback khi
        thanh toán THÀNH CÔNG** — không có callback thất bại, và trong `data` cũng không
        có trường mã kết quả nào để đọc. Đơn hỏng/bỏ dở thì đơn giản là không có callback,
        và `_expire_if_overdue` bên service dọn chúng.

        Điều đó AN TOÀN vì MAC ký bằng key2 phủ toàn bộ `data`, kể cả `amount` — không ai
        ngoài ZaloPay dựng được một payload qua cửa này. Bên service vẫn đối chiếu số tiền
        lần nữa trước khi kích hoạt gói.

        `data` không đọc được thì trả `success=False` kèm lý do, chứ không ném: bên gọi
        đã kiểm chữ ký xong, một payload đúng chữ ký mà sai định dạng là chuyện phải ghi
        nhận và điều tra, không phải 500 trần.
        """
        try:
            data = json.loads(payload.get("data") or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}

        app_trans_id = str(data.get("app_trans_id", ""))
        zp_trans_id = data.get("zp_trans_id")
        if not app_trans_id:
            return CallbackResult(
                order_id="",
                provider_reference=None,
                success=False,
                message="Callback ZaloPay thiếu app_trans_id.",
                amount=None,
            )
        return CallbackResult(
            order_id=order_id_from_app_trans_id(app_trans_id),
            provider_reference=str(zp_trans_id) if zp_trans_id is not None else None,
            success=True,
            message="Success",
            amount=_parse_amount(data.get("amount")),
        )

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        """Thân phản hồi ZaloPay chờ nhận lại từ webhook của ta.

        `return_code` = 1 nghĩa là "đã nhận, thôi gửi lại". Luôn trả 1 khi tới được đây:
        tới được đây tức là kết cục đã được ghi bền vào DB. Kể cả ca lệch tiền (service
        lật `success=False` rồi đánh dấu thất bại) cũng vẫn ack — gửi lại bao nhiêu lần
        thì số tiền vẫn lệch y như vậy, nên để ZaloPay retry chỉ tạo tiếng ồn chứ không
        sửa được gì. Việc cần làm ở ca đó là người vào xử tay, và service đã log `error`
        để gọi người.

        Chữ ký sai thì KHÔNG đi qua đây: service ném `InvalidPaymentSignatureError` từ
        trước, request hỏng, và ZaloPay tự retry — đúng thứ ta muốn cho một payload
        không xác thực được.
        """
        return {"return_code": 1, "return_message": "success"}

    def sign_callback(
        self,
        *,
        order_id: str,
        amount: Decimal | int,
        zp_trans_id: int | None = None,
        app_trans_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Dựng một callback ZaloPay ĐÚNG CHỮ KÝ — cho test và script mô phỏng local.

        Trả về đúng bao bì thật: `data` là chuỗi JSON, `mac` ký bằng key2 trên chính
        chuỗi đó, `type` = 1 (đơn hàng thường).
        """
        data = json.dumps(
            {
                "app_id": int(self.app_id),
                "app_trans_id": app_trans_id or build_app_trans_id(order_id, now=now),
                "app_time": int((now or datetime.now(UTC)).timestamp() * 1000),
                "app_user": self.app_user,
                "amount": int(amount),
                "embed_data": "{}",
                "item": "[]",
                "zp_trans_id": zp_trans_id if zp_trans_id is not None else int(time.time()),
                "server_time": int((now or datetime.now(UTC)).timestamp() * 1000),
                "channel": 36,
                "merchant_user_id": "solodesk",
                "user_fee_amount": 0,
                "discount_amount": 0,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return {"data": data, "mac": self._hmac(self.key2, data), "type": 1}


class ZaloPayClient(_ZaloPaySigned):
    """Client ZaloPay Open API v2 thật — gọi `/v2/create` trên sb-openapi.zalopay.vn.

    Hiện thực protocol `PaymentGateway` của module subscriptions.
    """

    def __init__(
        self,
        *,
        app_id: str,
        key1: str,
        key2: str,
        app_user: str,
        endpoint: str,
        query_endpoint: str,
        redirect_url: str,
        timeout_seconds: float,
        min_amount: int = ZALOPAY_MIN_AMOUNT_VND,
        max_amount: int = ZALOPAY_MAX_AMOUNT_VND,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.app_id = app_id
        self.key1 = key1
        self.key2 = key2
        self.app_user = app_user
        self.endpoint = endpoint
        self.query_endpoint = query_endpoint
        self.redirect_url = redirect_url
        self.timeout_seconds = timeout_seconds
        self.min_amount = min_amount
        self.max_amount = max_amount
        # Chỗ nối cho test tiêm `httpx.MockTransport` — None nghĩa là dùng mạng thật.
        self._transport = transport

    async def _post_form(self, url: str, body: dict[str, Any], *, op: str) -> httpx.Response:
        """POST form-urlencoded. Ném `PaymentGatewayError` khi KHÔNG GỌI TỚI ĐƯỢC.

        Ranh giới cố ý giữ hẹp: chỉ lỗi mạng (timeout, DNS, TLS, đứt kết nối) mới rơi vào
        đây. Một phản hồi 4xx/5xx CÓ THẬT là chuyện khác hẳn và được xử ở nơi gọi — gộp
        hai thứ đó vào một câu chính là gốc của sự cố "Không kết nối được" từng che mất
        một gói giá sai bên MoMo.
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as http_client:
                return await http_client.post(url, data=body)
        except httpx.HTTPError as exc:
            log.warning(
                f"zalopay.{op}_unreachable",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise PaymentGatewayError(
                "Không kết nối được tới ZaloPay lúc này. Bạn thử lại sau ít phút giúp mình nhé."
            ) from exc

    async def create_payment(
        self,
        *,
        order_id: str,
        amount: Decimal,
        currency: str,
        order_info: str,
        notify_url: str,
        redirect_url: str | None = None,
        order_code: str | None = None,
    ) -> CreatePaymentResult:
        body = self._build_create_body(
            order_id=order_id,
            amount=amount,
            currency=currency,
            order_info=order_info,
            notify_url=notify_url,
            redirect_url=redirect_url,
        )
        response = await self._post_form(self.endpoint, body, op="create_payment")
        data = _read_payload(response)

        # Một điều kiện cho CẢ HAI kiểu từ chối: mã HTTP 4xx/5xx và HTTP 200 kèm
        # `return_code != 1`. ZaloPay hay trả 200 cho cả từ chối nghiệp vụ, nên bỏ nhánh
        # sau là ghi nhận một đơn KHÔNG TỒN TẠI thành đơn tạo thành công, rồi đưa người
        # dùng tới một `order_url` rỗng.
        if response.is_error or not _is_success_code(data.get("return_code")):
            log.warning(
                "zalopay.create_payment_rejected",
                order_id=order_id,
                app_trans_id=body["app_trans_id"],
                amount=body["amount"],
                status_code=response.status_code,
                return_code=data.get("return_code"),
                sub_return_code=data.get("sub_return_code"),
                zalopay_message=data.get("sub_return_message") or data.get("return_message"),
            )
            raise PaymentGatewayError(_rejection_message(data, response.status_code))

        # `order_url` mở trang cổng ZaloPay trên trình duyệt; `zp_trans_token` là thứ SDK
        # mobile cần để mở thẳng app. Không có deeplink riêng như MoMo, nên ta dựng nó từ
        # token — app đọc token này là đủ.
        token = data.get("zp_trans_token") or data.get("order_token")
        return CreatePaymentResult(
            pay_url=data.get("order_url"),
            deeplink=f"zalopay://app?zptranstoken={token}" if token else None,
            qr_code_url=data.get("qr_code"),
            raw={**data, "app_trans_id": body["app_trans_id"]},
        )

    async def query_payment_status(self, order_id: str, app_trans_id: str) -> dict[str, Any]:
        """Hỏi thẳng ZaloPay xem đơn đã trả tiền chưa.

        MoMo không có đường này, nên luồng cũ phải tin vào callback và vào việc app mobile
        tự poll. ZaloPay có `/v2/query`, nghĩa là một callback thất lạc (tunnel dev sập,
        webhook chưa public) KHÔNG còn làm mất hẳn một giao dịch — có thể đối chiếu lại.

        Trả nguyên văn payload của ZaloPay: `return_code` 1 = đã trả tiền, 2 = thất bại,
        3 = chưa thực hiện/đang xử lý.
        """
        body = {
            "app_id": self.app_id,
            "app_trans_id": app_trans_id,
            "mac": self._sign_query(app_trans_id),
        }
        response = await self._post_form(self.query_endpoint, body, op="query_payment_status")
        data = _read_payload(response)
        if response.is_error and not data:
            raise PaymentGatewayError(_rejection_message(data, response.status_code))
        log.info(
            "zalopay.query_payment_status",
            order_id=order_id,
            app_trans_id=app_trans_id,
            return_code=data.get("return_code"),
        )
        return data


# Thông tin mock chỉ dùng cho dev — không bao giờ là thật, adapter này không gọi zalopay.vn.
_MOCK_APP_ID = "2554"
_MOCK_KEY1 = "mock-zalopay-key1-dev-only"
_MOCK_KEY2 = "mock-zalopay-key2-dev-only"
_MOCK_BASE_URL = "https://mock-payment.solodesk.dev/zalopay"


class MockZaloPayClient(_ZaloPaySigned):
    """Bản đứng thay hoàn toàn offline cho `ZaloPayClient` — cho test và dev local.

    Không bao giờ gọi zalopay.vn. Hình dạng request/response/callback bám đúng hợp đồng
    ZaloPay công bố, nên vòng ký–kiểm chữ ký ở đây là thật.
    """

    app_id = _MOCK_APP_ID
    key1 = _MOCK_KEY1
    key2 = _MOCK_KEY2
    app_user = "solodesk_user"
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
        order_code: str | None = None,
    ) -> CreatePaymentResult:
        body = self._build_create_body(
            order_id=order_id,
            amount=amount,
            currency=currency,
            order_info=order_info,
            notify_url=notify_url,
            redirect_url=redirect_url,
        )
        app_trans_id = body["app_trans_id"]
        token = f"MOCK{uuid.uuid4().hex[:20].upper()}"
        raw = {
            "return_code": 1,
            "return_message": "Giao dịch thành công",
            "sub_return_code": 1,
            "sub_return_message": "Giao dịch thành công",
            "zp_trans_token": token,
            "order_token": token,
            "order_url": f"{_MOCK_BASE_URL}/pay/{app_trans_id}",
            "qr_code": f"{_MOCK_BASE_URL}/qr/{app_trans_id}",
            "app_trans_id": app_trans_id,
            "mac": body["mac"],
        }
        return CreatePaymentResult(
            pay_url=raw["order_url"],
            deeplink=f"zalopay://app?zptranstoken={token}",
            qr_code_url=raw["qr_code"],
            raw=raw,
        )

    async def query_payment_status(self, order_id: str, app_trans_id: str) -> dict[str, Any]:
        return {
            "return_code": 3,
            "return_message": "Giao dịch chưa được thực hiện",
            "is_processing": True,
            "amount": 0,
            "zp_trans_id": 0,
            "discount_amount": 0,
        }
