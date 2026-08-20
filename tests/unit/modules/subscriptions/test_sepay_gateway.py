"""SePay adapter — header auth, order-code extraction, QR building, transfer direction.

Third sibling of `test_gateways.py` (MoMo) and `test_zalopay_gateway.py`. SePay is the
odd one out in this family and the tests below are mostly about the ways it differs:
authentication lives in a HEADER not the body, there is no outbound API call at all, and
the only link between money and an order is a short code in a bank transfer memo.
"""

import uuid
from decimal import Decimal

import pytest

from src.integrations.sepay.client import (
    MockSePayClient,
    PaymentGatewayError,
    SePayClient,
    extract_order_code,
)
from src.modules.subscriptions.domain.entities.subscription_payment import generate_order_code

_NOTIFY_URL = "https://api.solodesk.space/api/v1/payments/webhooks/sepay"
_API_KEY = "test-sepay-webhook-key"
_ORDER_CODE = "SD7K2M9PQR"


def _client(**overrides) -> SePayClient:
    kwargs = {
        "webhook_api_key": _API_KEY,
        "bank_code": "OCB",
        "account_number": "0123456789",
        "qr_base_url": "https://vietqr.app/img",
    }
    kwargs.update(overrides)
    return SePayClient(**kwargs)


async def _create(client, **overrides):
    kwargs = {
        "order_id": str(uuid.uuid4()),
        "amount": Decimal("199000"),
        "currency": "VND",
        "order_info": "SoloDesk Pro plan upgrade",
        "notify_url": _NOTIFY_URL,
        "order_code": _ORDER_CODE,
    }
    kwargs.update(overrides)
    return await client.create_payment(**kwargs)


# ---------------------------------------------------------------------------
# Xác thực: nằm ở HEADER, không phải trong thân request
# ---------------------------------------------------------------------------


def test_accepts_the_documented_authorization_header() -> None:
    """Nguyên văn tài liệu: ``Authorization: Apikey API_KEY_CUA_BAN``."""
    client = _client()

    assert client.verify_callback_signature({}, {"Authorization": f"Apikey {_API_KEY}"}) is True


def test_rejects_a_wrong_key() -> None:
    client = _client()

    assert client.verify_callback_signature({}, {"Authorization": "Apikey not-the-key"}) is False


@pytest.mark.parametrize(
    "header",
    [
        {},
        {"Authorization": ""},
        {"Authorization": _API_KEY},  # thiếu hẳn scheme
        {"Authorization": f"Bearer {_API_KEY}"},  # sai scheme
    ],
)
def test_rejects_malformed_authorization_headers(header: dict) -> None:
    assert _client().verify_callback_signature({}, header) is False


def test_header_scheme_match_is_case_insensitive() -> None:
    """Proxy và framework hay chuẩn hoá lại scheme của Authorization.

    Khoá thì so chính xác; chỉ riêng chữ "Apikey" mới bỏ qua hoa thường.
    """
    client = _client()

    assert client.verify_callback_signature({}, {"Authorization": f"APIKEY {_API_KEY}"}) is True
    assert client.verify_callback_signature({}, {"authorization": f"apikey {_API_KEY}"}) is True


def test_missing_headers_raises_instead_of_returning_false() -> None:
    """`headers=None` là LỖI ĐI DÂY, không phải "sai chữ ký".

    Trả `False` ở đây biến một router quên truyền header thành "mọi thanh toán thật đều
    sai xác thực" — triệu chứng không chỉ được về nguyên nhân. Phải ném.
    """
    with pytest.raises(PaymentGatewayError, match="did not pass them"):
        _client().verify_callback_signature({}, None)


def test_unconfigured_api_key_refuses_instead_of_accepting_everything() -> None:
    """Khoá rỗng + so sánh ngây thơ = nhận mọi callback không xác thực.

    Đây là ca xảy ra thật trên một môi trường quên set env, nên nó phải chết ồn ào.
    """
    with pytest.raises(PaymentGatewayError, match="not configured"):
        _client(webhook_api_key="").verify_callback_signature(
            {}, {"Authorization": "Apikey anything"}
        )


# ---------------------------------------------------------------------------
# Đọc mã đơn ra khỏi nội dung chuyển khoản
# ---------------------------------------------------------------------------


def test_reads_order_code_from_the_code_field() -> None:
    payload = MockSePayClient().build_webhook_payload(order_code=_ORDER_CODE, amount=199000)

    assert extract_order_code(payload) == _ORDER_CODE


def test_falls_back_to_scanning_content_when_code_field_is_null() -> None:
    """Trường `code` CHỈ có giá trị khi quy tắc tách mã ở dashboard được cấu hình đúng.

    Đó là một ô cấu hình trên web, không phải thứ code này kiểm soát. Cấu hình sai thì
    `code` về null và mọi khoản tiền vào thành mồ côi — trong khi mã vẫn nằm y nguyên
    trong `content`.
    """
    payload = MockSePayClient().build_webhook_payload(
        order_code=_ORDER_CODE, amount=199000, include_code_field=False
    )

    assert payload["code"] is None
    assert extract_order_code(payload) == _ORDER_CODE


def test_order_code_lookup_is_case_insensitive() -> None:
    """Một số ngân hàng viết thường hoá nội dung chuyển khoản."""
    assert extract_order_code({"code": None, "content": f"{_ORDER_CODE.lower()} chuyen tien"}) == (
        _ORDER_CODE
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"code": None, "content": "chuyen tien khong co ma"},
        {"code": "", "content": ""},
        {"code": None, "content": "SD123"},  # quá ngắn
        {},
    ],
)
def test_returns_empty_when_no_order_code_present(payload: dict) -> None:
    assert extract_order_code(payload) == ""


def test_generated_order_codes_are_recognised_by_the_extractor() -> None:
    """Chốt bảng chữ của `generate_order_code` khớp regex dò trong `content`.

    Hai hằng số này ở hai file khác nhau; lệch nhau thì một tỉ lệ nhất định các mã sinh
    ra sẽ không bao giờ dò lại được từ nội dung chuyển khoản.
    """
    for _ in range(200):
        code = generate_order_code()
        assert extract_order_code({"code": None, "content": f"{code} chuyen tien"}) == code


# ---------------------------------------------------------------------------
# parse_callback
# ---------------------------------------------------------------------------


def test_parse_callback_success_shape() -> None:
    client = MockSePayClient()
    payload = client.build_webhook_payload(order_code=_ORDER_CODE, amount=199000)

    result = client.parse_callback(payload)

    assert result.success is True
    assert result.order_id == _ORDER_CODE
    assert result.amount == Decimal("199000")
    assert result.provider_reference == "FT26082012345678"


def test_outgoing_transfer_is_never_a_payment() -> None:
    """`transferType` = "out" là tiền CHUYỂN ĐI.

    Bỏ kiểm này thì mỗi lần chủ tài khoản trả tiền cho ai đó, hệ thống lại ghi nhận một
    đơn được thanh toán — và số tiền hoàn toàn có thể tình cờ khớp.
    """
    client = MockSePayClient()
    payload = client.build_webhook_payload(
        order_code=_ORDER_CODE, amount=199000, transfer_type="out"
    )

    result = client.parse_callback(payload)

    assert result.success is False
    # Va KHONG actionable: mot khoan chuyen di khong bao gio ung voi don nao, nen ep no
    # phai khop se cho ra 404 va SePay gui lai mai.
    assert result.actionable is False


def test_incoming_transfer_without_order_code_is_reported_not_swallowed() -> None:
    """Tiền đã vào tài khoản THẬT nhưng không thuộc đơn nào.

    Khách chuyển nhầm, gõ sai mã, hoặc quy tắc tách mã bị sai. Phải ghi nhận để có người
    xử tay chứ không được lặng lẽ nuốt.
    """
    client = MockSePayClient()
    payload = client.build_webhook_payload(order_code="", amount=199000, include_code_field=False)
    payload["content"] = "chuyen tien khong ghi ma"

    result = client.parse_callback(payload)

    assert result.success is False
    assert result.order_id == ""
    assert result.amount == Decimal("199000")


def test_build_ack_response_is_what_sepay_expects() -> None:
    """Tài liệu nói rõ: thân `{"success": true}`. Route trả nó kèm HTTP 200."""
    client = MockSePayClient()
    parsed = client.parse_callback(
        client.build_webhook_payload(order_code=_ORDER_CODE, amount=199000)
    )

    assert client.build_ack_response(parsed) == {"success": True}


# ---------------------------------------------------------------------------
# create_payment — hoàn toàn cục bộ, không gọi mạng
# ---------------------------------------------------------------------------


async def test_create_payment_builds_a_vietqr_url_carrying_the_order_code() -> None:
    result = await _create(_client())

    assert result.qr_code_url.startswith("https://vietqr.app/img?")
    assert f"des={_ORDER_CODE}" in result.qr_code_url
    assert "acc=0123456789" in result.qr_code_url
    assert "bank=OCB" in result.qr_code_url
    assert "amount=199000" in result.qr_code_url
    # Chuyển khoản ngân hàng không có deeplink mở app nào để trỏ tới.
    assert result.deeplink is None


async def test_transfer_memo_is_exactly_the_order_code() -> None:
    """Thêm chữ vào `des` chỉ làm quy tắc tách mã ở dashboard mong manh hơn."""
    result = await _create(_client())

    des = result.qr_code_url.split("des=")[1].split("&")[0]
    assert des == _ORDER_CODE


async def test_create_payment_requires_an_order_code() -> None:
    """Không có mã đơn thì QR vẫn quét được, tiền vẫn vào, và KHÔNG BAO GIỜ khớp đơn nào."""
    with pytest.raises(PaymentGatewayError, match="order_code"):
        await _create(_client(), order_code=None)


async def test_create_payment_requires_account_configuration() -> None:
    with pytest.raises(PaymentGatewayError, match="SEPAY_ACCOUNT_NUMBER"):
        await _create(_client(account_number=""))


async def test_create_payment_rejects_non_vnd_currency() -> None:
    with pytest.raises(PaymentGatewayError, match="VND"):
        await _create(_client(), amount=Decimal("19"), currency="USD")


async def test_create_payment_rejects_fractional_amount() -> None:
    with pytest.raises(PaymentGatewayError, match="chẵn"):
        await _create(_client(), amount=Decimal("199000.50"))


@pytest.mark.parametrize("amount", ["999", "50000001"])
async def test_create_payment_rejects_out_of_range_amount(amount: str) -> None:
    with pytest.raises(PaymentGatewayError) as excinfo:
        await _create(_client(), amount=Decimal(amount))

    assert "1.000đ" in str(excinfo.value)


@pytest.mark.parametrize("amount", ["1000", "50000000"])
async def test_create_payment_accepts_exact_boundaries(amount: str) -> None:
    result = await _create(_client(), amount=Decimal(amount))

    assert result.qr_code_url


def test_mock_and_real_client_share_auth_and_parsing() -> None:
    """Bản mock chỉ được khác ở số tài khoản và khoá — không phải ở logic."""
    mock_type = type(MockSePayClient())
    assert mock_type.verify_callback_signature is SePayClient.verify_callback_signature
    assert mock_type.parse_callback is SePayClient.parse_callback
    assert mock_type.build_ack_response is SePayClient.build_ack_response
