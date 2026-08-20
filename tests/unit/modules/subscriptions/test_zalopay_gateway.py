"""ZaloPay adapter — signing, amount guards, callback parsing, HTTP error handling.

Sits beside `test_gateways.py` (the MoMo adapter's suite) on purpose: both cover the
same `PaymentGateway` port, and the two providers disagree on almost every detail that
matters — success code, key usage, callback envelope — so the pairing keeps the
differences visible.
"""

import hashlib
import hmac
import json
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from src.integrations.zalopay.client import (
    _MOCK_BASE_URL,
    MockZaloPayClient,
    PaymentGatewayError,
    ZaloPayClient,
    build_app_trans_id,
    order_id_from_app_trans_id,
)

_NOTIFY_URL = "https://api.solodesk.space/api/v1/payments/webhooks/zalopay"
_REDIRECT_URL = "https://app.solodesk.test/billing/result"
_KEY1 = "test-key1-outbound-request"
_KEY2 = "test-key2-inbound-callback"


def _client(transport: httpx.MockTransport | None = None, **overrides) -> ZaloPayClient:
    kwargs = {
        "app_id": "2554",
        "key1": _KEY1,
        "key2": _KEY2,
        "app_user": "solodesk_user",
        "endpoint": "https://sb-openapi.zalopay.vn/v2/create",
        "query_endpoint": "https://sb-openapi.zalopay.vn/v2/query",
        "redirect_url": _REDIRECT_URL,
        "timeout_seconds": 5.0,
        "transport": transport,
    }
    kwargs.update(overrides)
    return ZaloPayClient(**kwargs)


def _form(request: httpx.Request) -> dict[str, str]:
    """Body form-urlencoded của một request đã bắt được, dạng dict."""
    return dict(urllib.parse.parse_qsl(request.content.decode()))


def _ok_response(**overrides) -> dict:
    payload = {
        "return_code": 1,
        "return_message": "Giao dịch thành công",
        "sub_return_code": 1,
        "sub_return_message": "Giao dịch thành công",
        "zp_trans_token": "ACeZ5GMaVO1EkIMrYtxX9hng",
        "order_token": "ACeZ5GMaVO1EkIMrYtxX9hng",
        "order_url": "https://qcgateway.zalopay.vn/openinapp?order=eyJ6cCI6MX0=",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# app_trans_id — hạn mức 40 ký tự và tiền tố ngày theo giờ Việt Nam
# ---------------------------------------------------------------------------


def test_app_trans_id_fits_zalopay_length_limit() -> None:
    """Chỗ thiết kế hiện tại đâm vào ZaloPay.

    `SubscriptionPayment.id` là UUID và được dùng LUÔN làm mã đơn. `yymmdd_` + UUID có
    gạch ngang = 43 ký tự, vượt trần 40 của `app_trans_id`. Bỏ gạch ngang mới vừa.
    """
    trans_id = build_app_trans_id(str(uuid.uuid4()))

    assert len(trans_id) <= 40
    assert len(trans_id) == 39


def test_app_trans_id_starts_with_vietnam_date_not_utc_date() -> None:
    """00:30 giờ Việt = 17:30 UTC NGÀY HÔM TRƯỚC.

    Lấy ngày theo UTC ở đây là gửi sai tiền tố và ZaloPay từ chối đơn — nhưng chỉ trong
    7 tiếng mỗi ngày, nên nó lọt qua mọi lần chạy thử ban ngày.
    """
    just_after_midnight_ict = datetime(2026, 8, 20, 0, 30, tzinfo=timezone(timedelta(hours=7)))

    trans_id = build_app_trans_id(str(uuid.uuid4()), now=just_after_midnight_ict)

    assert trans_id.startswith("260820_")
    assert just_after_midnight_ict.astimezone(UTC).strftime("%y%m%d") == "260819"


def test_app_trans_id_round_trips_back_to_a_parseable_uuid() -> None:
    """`handle_payment_callback` gọi thẳng `uuid.UUID(parsed.order_id)`.

    Nếu vòng đi–về không trả lại thứ UUID đọc được, mọi callback ZaloPay thành 404
    "Unknown order" dù tiền đã thu.
    """
    order_id = str(uuid.uuid4())

    recovered = order_id_from_app_trans_id(build_app_trans_id(order_id))

    assert uuid.UUID(recovered) == uuid.UUID(order_id)


def test_app_trans_id_accepts_non_uuid_order_id_and_still_fits() -> None:
    trans_id = build_app_trans_id("order-" + "x" * 90)

    assert len(trans_id) <= 40
    assert trans_id.split("_", 1)[1].startswith("orderxxx")


def test_order_id_from_app_trans_id_without_separator_returns_input() -> None:
    assert order_id_from_app_trans_id("260820abcdef") == "260820abcdef"


# ---------------------------------------------------------------------------
# create_payment — hình dạng kết quả và các chốt chặn số tiền
# ---------------------------------------------------------------------------


async def test_create_payment_returns_success_shape() -> None:
    client = MockZaloPayClient()
    order_id = str(uuid.uuid4())

    result = await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url=_NOTIFY_URL,
    )

    assert result.pay_url and result.pay_url.startswith(_MOCK_BASE_URL)
    assert result.deeplink and result.deeplink.startswith("zalopay://app?zptranstoken=")
    assert result.qr_code_url
    assert result.raw["return_code"] == 1
    assert uuid.UUID(order_id_from_app_trans_id(result.raw["app_trans_id"])) == uuid.UUID(order_id)


async def test_create_payment_rejects_non_vnd_currency() -> None:
    with pytest.raises(PaymentGatewayError, match="VND"):
        await MockZaloPayClient().create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("19"),
            currency="USD",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )


async def test_create_payment_rejects_fractional_amount() -> None:
    with pytest.raises(PaymentGatewayError, match="chẵn"):
        await MockZaloPayClient().create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000.50"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )


@pytest.mark.parametrize("amount", ["999", "50000001"])
async def test_create_payment_rejects_out_of_range_amount(amount: str) -> None:
    with pytest.raises(PaymentGatewayError) as excinfo:
        await MockZaloPayClient().create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal(amount),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )

    # Câu báo phải nói ra CON SỐ, định dạng kiểu Việt — nó đi thẳng ra toast đỏ.
    assert "1.000đ" in str(excinfo.value)


@pytest.mark.parametrize("amount", ["1000", "50000000"])
async def test_create_payment_accepts_exact_boundaries(amount: str) -> None:
    result = await MockZaloPayClient().create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal(amount),
        currency="VND",
        order_info="x",
        notify_url=_NOTIFY_URL,
    )

    assert result.pay_url


async def test_real_client_never_calls_zalopay_for_out_of_range_amount() -> None:
    """Chốt chặn phải bắn TRƯỚC khi rời tiến trình.

    Để lọt ra ngoài thì ZaloPay trả một mã lỗi trần, và người dùng thấy một câu vô nghĩa
    thay vì "giá gói sai".
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_ok_response())

    with pytest.raises(PaymentGatewayError):
        await _client(httpx.MockTransport(handler)).create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("200"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )

    assert calls == []


# ---------------------------------------------------------------------------
# redirect_url — nằm trong embed_data, và không bao giờ được trùng notify_url
# ---------------------------------------------------------------------------


async def test_redirect_url_travels_inside_embed_data() -> None:
    """ZaloPay không có tham số redirect riêng ở cấp cao nhất như MoMo."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(_form(request))
        return httpx.Response(200, json=_ok_response())

    await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="x",
        notify_url=_NOTIFY_URL,
        redirect_url="https://app.solodesk.test/per-call",
    )

    assert json.loads(captured["embed_data"])["redirecturl"] == "https://app.solodesk.test/per-call"


async def test_falls_back_to_configured_redirect_when_none_given() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(_form(request))
        return httpx.Response(200, json=_ok_response())

    await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="x",
        notify_url=_NOTIFY_URL,
    )

    assert json.loads(captured["embed_data"])["redirecturl"] == _REDIRECT_URL


async def test_raises_when_redirect_would_equal_notify_url() -> None:
    """Trỏ trình duyệt vào webhook chỉ-nhận-POST = người dùng bấm huỷ và rơi vào 405."""
    with pytest.raises(PaymentGatewayError, match="differ from"):
        await MockZaloPayClient().create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
            redirect_url=_NOTIFY_URL,
        )


async def test_raises_when_no_redirect_configured() -> None:
    with pytest.raises(PaymentGatewayError, match="must be configured"):
        await _client(redirect_url="").create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )


# ---------------------------------------------------------------------------
# Chữ ký — key1 cho request đi ra, key2 cho callback đi vào
# ---------------------------------------------------------------------------


async def test_create_request_mac_is_signed_with_key1_over_documented_field_order() -> None:
    """hmacinput = app_id|app_trans_id|app_user|amount|app_time|embed_data|item

    Tính lại tay bằng key1 và so — nếu ai đó đổi thứ tự trường hoặc đổi sang key2 thì
    ZaloPay từ chối mọi đơn, và triệu chứng ở phía ta chỉ là một mã lỗi trần.
    """
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(_form(request))
        return httpx.Response(200, json=_ok_response())

    await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url=_NOTIFY_URL,
    )

    raw = (
        f"{captured['app_id']}|{captured['app_trans_id']}|{captured['app_user']}|"
        f"{captured['amount']}|{captured['app_time']}|{captured['embed_data']}|{captured['item']}"
    )
    assert captured["mac"] == hmac.new(_KEY1.encode(), raw.encode(), hashlib.sha256).hexdigest()
    assert captured["mac"] != hmac.new(_KEY2.encode(), raw.encode(), hashlib.sha256).hexdigest()


async def test_create_request_is_form_encoded_not_json() -> None:
    """ZaloPay Open API nhận `application/x-www-form-urlencoded`.

    Gửi JSON thì mọi trường về rỗng phía họ, chữ ký "sai", và không có gì trong thông báo
    lỗi chỉ được tới nguyên nhân.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_ok_response())

    await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="x",
        notify_url=_NOTIFY_URL,
    )

    assert captured[0].headers["content-type"].startswith("application/x-www-form-urlencoded")


def test_callback_mac_uses_key2_and_rejects_a_key1_signature() -> None:
    """Hai khoá KHÔNG hoán đổi được. Ký nhầm bằng key1 thì mọi thanh toán thật bị từ chối."""
    client = _client()
    payload = client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)

    assert client.verify_callback_signature(payload) is True

    forged = {
        **payload,
        "mac": hmac.new(_KEY1.encode(), payload["data"].encode(), hashlib.sha256).hexdigest(),
    }
    assert client.verify_callback_signature(forged) is False


def test_sign_callback_round_trips_through_verify() -> None:
    client = MockZaloPayClient()

    assert client.verify_callback_signature(
        client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)
    )


def test_verify_rejects_tampered_amount() -> None:
    """MAC phủ toàn bộ `data`, kể cả `amount` — đây là thứ khiến `success=True` mặc định
    trong `parse_callback` là an toàn."""
    client = MockZaloPayClient()
    payload = client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)
    payload["data"] = payload["data"].replace('"amount":199000', '"amount":1000')

    assert client.verify_callback_signature(payload) is False


def test_verify_rejects_tampered_mac() -> None:
    client = MockZaloPayClient()
    payload = client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)

    assert client.verify_callback_signature({**payload, "mac": "0" * 64}) is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": "{}"},
        {"mac": "abc"},
        {"data": {"app_trans_id": "x"}, "mac": "abc"},
        {"data": "{}", "mac": None},
    ],
)
def test_verify_rejects_malformed_envelopes(payload: dict) -> None:
    """Không có `data`/`mac` dạng chuỗi thì trả False, KHÔNG ném — một request rác không
    được phép thành 500."""
    assert MockZaloPayClient().verify_callback_signature(payload) is False


# ---------------------------------------------------------------------------
# parse_callback
# ---------------------------------------------------------------------------


def test_parse_callback_returns_order_id_the_service_can_look_up() -> None:
    client = MockZaloPayClient()
    order_id = str(uuid.uuid4())
    payload = client.sign_callback(order_id=order_id, amount=199000, zp_trans_id=240820000001)

    result = client.parse_callback(payload)

    assert uuid.UUID(result.order_id) == uuid.UUID(order_id)
    assert result.provider_reference == "240820000001"
    assert result.success is True
    assert result.amount == Decimal("199000")


def test_parse_callback_reports_failure_when_app_trans_id_missing() -> None:
    """Đúng chữ ký nhưng sai định dạng: ghi nhận và điều tra, không 500 trần."""
    client = MockZaloPayClient()
    data = json.dumps({"amount": 199000})
    payload = {"data": data, "mac": client._hmac(client.key2, data)}

    result = client.parse_callback(payload)

    assert result.success is False
    assert "app_trans_id" in result.message


def test_parse_callback_survives_unparsable_data() -> None:
    result = MockZaloPayClient().parse_callback({"data": "not-json", "mac": "x"})

    assert result.success is False


def test_build_ack_response_is_what_zalopay_expects() -> None:
    client = MockZaloPayClient()
    parsed = client.parse_callback(client.sign_callback(order_id=str(uuid.uuid4()), amount=1000))

    assert client.build_ack_response(parsed) == {"return_code": 1, "return_message": "success"}


# ---------------------------------------------------------------------------
# Client thật — ranh giới giữa "bị từ chối" và "không gọi tới được"
# ---------------------------------------------------------------------------


async def test_real_client_returns_gateway_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_response())

    result = await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url=_NOTIFY_URL,
    )

    assert result.pay_url == "https://qcgateway.zalopay.vn/openinapp?order=eyJ6cCI6MX0="
    assert result.deeplink == "zalopay://app?zptranstoken=ACeZ5GMaVO1EkIMrYtxX9hng"


async def test_http_200_with_failure_return_code_is_a_rejection() -> None:
    """ZaloPay hay trả 200 cho cả từ chối nghiệp vụ.

    Bỏ qua nhánh này là ghi nhận một đơn KHÔNG TỒN TẠI thành đơn tạo thành công, rồi đưa
    người dùng tới một `order_url` rỗng.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "return_code": 2,
                "return_message": "Giao dịch thất bại",
                "sub_return_code": -401,
                "sub_return_message": "Merchant is not exist",
            },
        )

    with pytest.raises(PaymentGatewayError) as excinfo:
        await _client(httpx.MockTransport(handler)).create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )

    assert "Merchant is not exist" in str(excinfo.value)
    assert "-401" in str(excinfo.value)


async def test_http_400_is_reported_as_rejection_not_network_failure() -> None:
    """Thân JSON phải được đọc CẢ KHI mã HTTP là 4xx — đó là chỗ ghi lý do thật."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"return_code": 2, "sub_return_message": "Invalid amount"})

    with pytest.raises(PaymentGatewayError) as excinfo:
        await _client(httpx.MockTransport(handler)).create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )

    assert "Invalid amount" in str(excinfo.value)
    assert "Không kết nối được" not in str(excinfo.value)


async def test_http_error_without_json_body_still_names_the_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad Gateway</html>")

    with pytest.raises(PaymentGatewayError) as excinfo:
        await _client(httpx.MockTransport(handler)).create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )

    assert "502" in str(excinfo.value)


async def test_network_error_is_reported_as_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(PaymentGatewayError, match="Không kết nối được"):
        await _client(httpx.MockTransport(handler)).create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="x",
            notify_url=_NOTIFY_URL,
        )


async def test_return_code_as_string_still_counts_as_success() -> None:
    """Một khâu trung gian biến số thành chuỗi là đủ để `== 1` ra False — và một đơn tạo
    THÀNH CÔNG bị coi là hỏng."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_response(return_code="1"))

    result = await _client(httpx.MockTransport(handler)).create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="x",
        notify_url=_NOTIFY_URL,
    )

    assert result.pay_url


# ---------------------------------------------------------------------------
# query_payment_status — đường MoMo không có
# ---------------------------------------------------------------------------


async def test_query_payment_status_signs_with_key1_and_returns_payload() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(_form(request))
        return httpx.Response(200, json={"return_code": 1, "amount": 199000, "zp_trans_id": 7})

    order_id = str(uuid.uuid4())
    app_trans_id = build_app_trans_id(order_id)

    data = await _client(httpx.MockTransport(handler)).query_payment_status(order_id, app_trans_id)

    expected = hmac.new(
        _KEY1.encode(), f"2554|{app_trans_id}|{_KEY1}".encode(), hashlib.sha256
    ).hexdigest()
    assert captured["mac"] == expected
    assert data["return_code"] == 1


async def test_query_payment_status_reports_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(PaymentGatewayError, match="Không kết nối được"):
        await _client(httpx.MockTransport(handler)).query_payment_status("x", "260820_x")


def test_mock_and_real_client_share_signing_logic() -> None:
    """Bản mock chỉ được khác ở chỗ KHÔNG đi mạng — nếu nó tự ký kiểu riêng thì test dựa
    trên nó không còn chứng minh được gì về client thật."""
    mock_type = type(MockZaloPayClient())
    assert mock_type.verify_callback_signature is ZaloPayClient.verify_callback_signature
    assert mock_type.parse_callback is ZaloPayClient.parse_callback
    assert mock_type._sign_create is ZaloPayClient._sign_create
