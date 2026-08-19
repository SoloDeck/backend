import json
import uuid
from decimal import Decimal

import httpx
import pytest

from src.integrations.momo.client import (
    _MOCK_BASE_URL,
    MockMomoClient,
    MomoClient,
    PaymentGatewayError,
)


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
        redirect_url="https://app.solodesk.test/billing/result",
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


def test_parse_callback_accepts_result_code_as_string() -> None:
    """`resultCode` về dạng chuỗi `"0"` vẫn phải hiểu là THÀNH CÔNG.

    Bản trước so thẳng `== 0` nên `"0"` ra False — thanh toán thành công bị ghi nhận là
    thất bại. Chữ ký vẫn khớp (chuỗi ký nội suy resultCode thành text ở cả hai phía), nên
    không lớp kiểm nào bắt được.  #Huynh
    """
    client = MockMomoClient()
    payload = client.sign_ipn(order_id="order-1", amount=100000, trans_id=999)
    payload["resultCode"] = str(payload["resultCode"])

    result = client.parse_callback(payload)

    assert result.success is True


def test_parse_callback_treats_unparsable_result_code_as_failure() -> None:
    """Không đọc nổi thì coi là thất bại — thà không kích hoạt còn hơn kích hoạt nhầm."""
    client = MockMomoClient()
    payload = client.sign_ipn(order_id="order-1", amount=100000)
    payload["resultCode"] = "khong-phai-so"

    assert client.parse_callback(payload).success is False

    del payload["resultCode"]
    assert client.parse_callback(payload).success is False


def test_build_ack_response_shape() -> None:
    client = MockMomoClient()
    payload = client.sign_ipn(order_id="order-1", amount=100000)
    result = client.parse_callback(payload)

    ack = client.build_ack_response(result)

    assert ack["orderId"] == "order-1"
    assert ack["resultCode"] == 0


async def test_create_payment_uses_given_redirect_url_over_notify_url() -> None:
    client = MockMomoClient()

    result = await client.create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        redirect_url="https://app.solodesk.space/billing/result",
    )

    assert result.raw["redirectUrl"] == "https://app.solodesk.space/billing/result"


async def test_create_payment_falls_back_to_configured_default_when_no_redirect_given() -> None:
    client = MockMomoClient()
    notify_url = "https://api.solodesk.space/api/v1/payments/webhooks/momo"

    result = await client.create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url=notify_url,
    )

    assert result.raw["redirectUrl"] == f"{_MOCK_BASE_URL}/result"
    assert result.raw["redirectUrl"] != notify_url


async def test_create_payment_raises_when_redirect_would_equal_notify_url() -> None:
    client = MockMomoClient()
    notify_url = "https://api.solodesk.space/api/v1/payments/webhooks/momo"

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url=notify_url,
            redirect_url=notify_url,
        )


async def test_create_payment_raises_when_no_redirect_configured() -> None:
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

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


async def test_real_client_prefers_per_call_redirect_url_over_configured_default() -> None:
    order_id = str(uuid.uuid4())
    sent_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent_body.update(json.loads(request.read()))
        return httpx.Response(
            200,
            json={
                "partnerCode": "MOMO",
                "orderId": order_id,
                "requestId": sent_body["requestId"],
                "resultCode": 0,
                "message": "Success",
                "payUrl": f"https://test-payment.momo.vn/pay/{order_id}",
                "deeplink": f"momo://app?orderId={order_id}",
                "qrCodeUrl": f"https://test-payment.momo.vn/qr/{order_id}",
            },
        )

    client = MomoClient(
        partner_code="MOMO",
        access_key="access-key",
        secret_key="secret-key",
        partner_name="SoloDesk",
        store_id="SoloDeskStore",
        endpoint="https://test-payment.momo.vn/v2/gateway/api/create",
        request_type="captureWallet",
        lang="vi",
        redirect_url="https://configured-default.example/result",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        redirect_url="https://per-call.example/result",
    )

    assert sent_body["redirectUrl"] == "https://per-call.example/result"


async def test_real_client_uses_configured_default_when_no_redirect_given() -> None:
    order_id = str(uuid.uuid4())
    sent_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent_body.update(json.loads(request.read()))
        return httpx.Response(
            200,
            json={
                "partnerCode": "MOMO",
                "orderId": order_id,
                "requestId": sent_body["requestId"],
                "resultCode": 0,
                "message": "Success",
                "payUrl": f"https://test-payment.momo.vn/pay/{order_id}",
                "deeplink": f"momo://app?orderId={order_id}",
                "qrCodeUrl": f"https://test-payment.momo.vn/qr/{order_id}",
            },
        )

    client = MomoClient(
        partner_code="MOMO",
        access_key="access-key",
        secret_key="secret-key",
        partner_name="SoloDesk",
        store_id="SoloDeskStore",
        endpoint="https://test-payment.momo.vn/v2/gateway/api/create",
        request_type="captureWallet",
        lang="vi",
        redirect_url="https://configured-default.example/result",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert sent_body["redirectUrl"] == "https://configured-default.example/result"


async def test_create_payment_rejects_non_vnd_currency() -> None:
    client = MockMomoClient()

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="USD",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


async def test_create_payment_rejects_fractional_amount() -> None:
    client = MockMomoClient()

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000.50"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


async def test_real_client_rejects_invalid_amount_before_calling_momo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("MoMo should never be called for an invalid amount/currency")

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="USD",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


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
    """Lỗi mạng thật phải nói là lỗi mạng — và CHỈ lỗi mạng mới được nói vậy.

    Cặp với `test_http_400_is_reported_as_rejection_not_network_failure`: hai test này
    giữ hai đầu của ranh giới từng bị gộp làm một.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError) as excinfo:
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )

    assert "Không kết nối được tới MoMo" in excinfo.value.message


# ---------------------------------------------------------------------------
# Hạn mức số tiền của MoMo (1.000đ – 50.000.000đ)
#
# Sự cố gốc: một gói dịch vụ để giá 200đ. Không tầng nào đặt giá sàn, nên số tiền đó đi
# thẳng lên MoMo, MoMo trả HTTP 400, và người dùng nhận được câu "Could not reach MoMo"
# — vừa không nói được nguyên nhân, vừa chỉ sai hướng.
# ---------------------------------------------------------------------------


async def test_create_payment_rejects_amount_below_momo_minimum() -> None:
    """Đúng con số đã gây ra sự cố."""
    client = MockMomoClient()

    with pytest.raises(PaymentGatewayError) as excinfo:
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("200"),
            currency="VND",
            order_info="SoloDesk abc plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )

    message = excinfo.value.message
    assert "1.000" in message and "200" in message


async def test_create_payment_rejects_amount_above_momo_maximum() -> None:
    client = MockMomoClient()

    with pytest.raises(PaymentGatewayError) as excinfo:
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("50000001"),
            currency="VND",
            order_info="SoloDesk Enterprise plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )

    assert "50.000.000" in excinfo.value.message


@pytest.mark.parametrize("amount", ["1000", "50000000"])
async def test_create_payment_accepts_exact_momo_boundaries(amount: str) -> None:
    """Hai biên phải ĐI LỌT — chặn quá tay một đồng cũng là một lỗi khác."""
    client = MockMomoClient()

    result = await client.create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal(amount),
        currency="VND",
        order_info="SoloDesk plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert result.raw["amount"] == int(amount)


async def test_real_client_never_calls_momo_for_out_of_range_amount() -> None:
    """Chặn phải xảy ra TRƯỚC khi rời tiến trình.

    Đây là điểm mấu chốt: dữ liệu cũ trong DB (gói 200đ tạo trước bản vá) không được
    phép bắn lên MoMo để đổi lấy một cái 400 rồi hiện ra thành lỗi mạng.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("MoMo không được gọi khi số tiền nằm ngoài hạn mức")

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError):
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("200"),
            currency="VND",
            order_info="SoloDesk abc plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )


# ---------------------------------------------------------------------------
# MoMo từ chối ≠ không gọi tới được MoMo
# ---------------------------------------------------------------------------


async def test_http_400_is_reported_as_rejection_not_network_failure() -> None:
    """Test hồi quy cho chính câu báo lỗi đã gây hiểu nhầm.

    `raise_for_status()` từng ném `HTTPStatusError` — lớp con của `HTTPError` — vào đúng
    khối `except` dành cho lỗi mạng, nên một cái 400 hiện ra thành "Could not reach
    MoMo", và thân JSON nói rõ lý do thì bị vứt trước khi kịp đọc.

    Phản hồi dựng ở đây là phản hồi THẬT của MoMo sandbox khi gửi ``amount: 200`` — chép
    nguyên văn, kể cả `resultCode` 22. Vì request gửi kèm ``lang=vi`` nên câu giải thích
    vốn đã là tiếng Việt: chỉ cần đọc ra là dùng được ngay, không phải dịch hộ.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "requestId": json.loads(request.read())["requestId"],
                "responseTime": 1786432531724,
                "resultCode": 22,
                "message": (
                    "Yêu cầu bị từ chối vì số tiền giao dịch nhỏ hơn số tiền tối thiểu "
                    "cho phép là 1000 VND hoặc lớn hơn số tiền tối đa cho phép là "
                    "50000000 VND."
                ),
            },
        )

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError) as excinfo:
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )

    message = excinfo.value.message
    assert "số tiền giao dịch nhỏ hơn số tiền tối thiểu" in message
    assert "22" in message
    assert "kết nối" not in message


async def test_http_error_without_json_body_still_names_the_status() -> None:
    """MoMo qua proxy/WAF có thể trả HTML. Không được nổ thêm `ValueError` từ `.json()`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html><body>Bad Gateway</body></html>")

    client = _momo_client(httpx.MockTransport(handler))

    with pytest.raises(PaymentGatewayError) as excinfo:
        await client.create_payment(
            order_id=str(uuid.uuid4()),
            amount=Decimal("199000"),
            currency="VND",
            order_info="SoloDesk Pro plan upgrade",
            notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
        )

    assert "502" in excinfo.value.message


async def test_result_code_zero_as_string_still_counts_as_success() -> None:
    """`_is_success_code` xử được `"0"` dạng chuỗi; nhánh tạo thanh toán nay dùng chung nó."""
    order_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resultCode": "0",
                "message": "Success",
                "payUrl": f"https://test-payment.momo.vn/pay/{order_id}",
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


# ---------------------------------------------------------------------------
# orderInfo được nội suy vào chuỗi ký
# ---------------------------------------------------------------------------


async def test_order_info_strips_signature_delimiters() -> None:
    """Tên gói chứa `&`/`=` không được lọt vào chuỗi ký nguyên trạng."""
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.read()))
        return httpx.Response(200, json={"resultCode": 0, "message": "Success", "payUrl": "https://x"})

    client = _momo_client(httpx.MockTransport(handler))

    await client.create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk A&B=C plan upgrade",
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert "&" not in sent["orderInfo"]
    assert "=" not in sent["orderInfo"]
    assert "SoloDesk A" in sent["orderInfo"]


async def test_order_info_truncated_to_momo_limit() -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.read()))
        return httpx.Response(200, json={"resultCode": 0, "message": "Success", "payUrl": "https://x"})

    client = _momo_client(httpx.MockTransport(handler))

    await client.create_payment(
        order_id=str(uuid.uuid4()),
        amount=Decimal("199000"),
        currency="VND",
        order_info="x" * 400,
        notify_url="https://api.solodesk.space/api/v1/payments/webhooks/momo",
    )

    assert len(sent["orderInfo"]) == 255


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
