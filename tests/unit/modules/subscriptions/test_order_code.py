"""Mã đơn ngắn (`order_code`) và việc nới protocol `PaymentGateway`.

Hai thay đổi này chưa có cổng nào dùng tới — chúng là nền cho cổng đối soát ngân hàng.
Test ở đây giữ đúng hai tính chất mà cổng đó sẽ dựa vào, và giữ luôn lời hứa "MoMo với
ZaloPay không đổi hành vi".
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.integrations.momo.client import MockMomoClient
from src.integrations.zalopay.client import MockZaloPayClient
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import (
    ORDER_CODE_BODY_LENGTH,
    ORDER_CODE_PREFIX,
    generate_order_code,
)

# Những ký tự bị loại khỏi bảng chữ, và lý do chúng bị loại.
_AMBIGUOUS = "ILOU"


def test_order_code_shape() -> None:
    code = generate_order_code()

    assert code.startswith(ORDER_CODE_PREFIX)
    assert len(code) == len(ORDER_CODE_PREFIX) + ORDER_CODE_BODY_LENGTH
    # Phải vừa cột String(16) — xem migration b2c3d4e5f6a7.
    assert len(code) <= 16


def test_order_code_avoids_characters_that_get_mistyped() -> None:
    """Mã này được ĐỌC TỪ MÀN HÌNH RỒI GÕ TAY vào ô nội dung chuyển khoản.

    I/L lẫn với 1, O lẫn với 0. Mỗi cặp nhìn giống nhau là một khoản tiền vào không khớp
    được đơn nào — và không ai biết vì sao, vì phía ngân hàng nội dung trông vẫn "đúng".
    """
    body = "".join(generate_order_code()[len(ORDER_CODE_PREFIX) :] for _ in range(500))

    assert not set(body) & set(_AMBIGUOUS)
    assert set(body) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_order_codes_do_not_repeat_in_practice() -> None:
    """Không phải chứng minh toán học — chỉ chặn ca sinh ra hằng số hoặc bộ đếm."""
    codes = {generate_order_code() for _ in range(2000)}

    assert len(codes) == 2000


async def test_callback_lookup_uses_uuid_path_when_order_id_is_a_uuid() -> None:
    """MoMo/ZaloPay trả lại chính `payment.id`, nên phải đi đường khoá theo id."""
    repo = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo)
    payment_id = uuid.uuid4()

    await service._payment_for_callback(str(payment_id))

    repo.get_payment_by_id_for_update.assert_awaited_once_with(payment_id)
    repo.get_payment_by_order_code_for_update.assert_not_awaited()


async def test_callback_lookup_falls_back_to_order_code() -> None:
    """Bản trước ném thẳng 404 cho mọi mã không phải UUID.

    Cổng đối soát ngân hàng chỉ biết mã ngắn, nên nhánh đó phải tra `order_code` chứ
    không được từ chối — nếu không, tiền vào thật mà không đơn nào được kích hoạt.
    """
    repo = AsyncMock()
    service = SubscriptionsService(db=AsyncMock(), repo=repo)

    await service._payment_for_callback("SD7K2M9P")

    repo.get_payment_by_order_code_for_update.assert_awaited_once_with("SD7K2M9P")
    repo.get_payment_by_id_for_update.assert_not_awaited()


@pytest.mark.parametrize("client", [MockMomoClient(), MockZaloPayClient()])
def test_existing_adapters_ignore_headers(client) -> None:
    """Nới protocol KHÔNG được đổi hành vi của hai cổng ký-trong-thân.

    Cả khi không truyền header, khi truyền rỗng, và khi truyền một header vô nghĩa, kết
    quả xác thực phải y hệt nhau — chữ ký của chúng nằm trong payload.
    """
    payload = (
        client.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)
        if isinstance(client, MockMomoClient)
        else client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)
    )

    assert client.verify_callback_signature(payload) is True
    assert client.verify_callback_signature(payload, {}) is True
    assert client.verify_callback_signature(payload, {"Authorization": "Apikey rác"}) is True


@pytest.mark.parametrize("client", [MockMomoClient(), MockZaloPayClient()])
def test_existing_adapters_still_reject_tampered_payloads_with_headers(client) -> None:
    """Và header hợp lệ KHÔNG được cứu một payload sai chữ ký."""
    payload = (
        client.sign_ipn(order_id=str(uuid.uuid4()), amount=199000)
        if isinstance(client, MockMomoClient)
        else client.sign_callback(order_id=str(uuid.uuid4()), amount=199000)
    )
    key = "signature" if isinstance(client, MockMomoClient) else "mac"
    payload[key] = "0" * 64

    assert client.verify_callback_signature(payload, {"Authorization": "Apikey hop-le"}) is False
