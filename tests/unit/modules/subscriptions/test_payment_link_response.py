"""`payment_link.type` phải nói đúng bản chất của `url`, và SePay phải kèm hướng dẫn.

Đây là hợp đồng giữa backend và client. Bản trước hard-code `type="checkout_url"` cho
mọi cổng, nên với SePay client được bảo "đây là URL thanh toán" trong khi `url` là một
tấm ảnh PNG.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.modules.subscriptions.schemas.response import PaymentIntentResponse


def _row(**overrides):
    now = datetime.now(UTC)
    base = dict(
        id=uuid.uuid4(),
        subscription_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        provider="sepay",
        status="pending",
        amount=Decimal("199000.00"),
        currency="VND",
        order_code="SDDYFM83AS",
        pay_url="https://vietqr.app/img?acc=40104887&bank=ACB&amount=199000&des=SDDYFM83AS",
        qr_code_url="https://vietqr.app/img?acc=40104887&bank=ACB&amount=199000&des=SDDYFM83AS",
        deeplink=None,
        raw_create_response={
            "order_code": "SDDYFM83AS",
            "amount": 199000,
            "bank": "ACB",
            "account_number": "40104887",
        },
        provider_reference=None,
        paid_at=None,
        expires_at=now,
        failure_reason=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_sepay_is_not_advertised_as_a_checkout_url() -> None:
    """`url` là ảnh PNG. Client tin vào `type` sẽ điều hướng trình duyệt vào file ảnh."""
    resp = PaymentIntentResponse.from_model(_row())

    assert resp.payment_link.type == "bank_transfer_instruction"


def test_sepay_instructions_carry_everything_needed_to_pay_by_hand() -> None:
    """Quét QR hỏng là chuyện thường — lúc đó bốn con số này là thứ duy nhất cứu giao dịch."""
    resp = PaymentIntentResponse.from_model(_row())

    text = resp.payment_link.instructions
    assert text is not None
    assert "40104887" in text
    assert "ACB" in text
    assert "SDDYFM83AS" in text
    assert "199.000" in text  # định dạng nghìn theo lối Việt


def test_order_code_is_a_real_field_not_a_query_string_to_parse() -> None:
    """Trước bản này mã đơn CHỈ tồn tại trong query string của ảnh QR."""
    resp = PaymentIntentResponse.from_model(_row())

    assert resp.order_code == "SDDYFM83AS"


def test_sepay_instructions_are_none_when_the_raw_payload_is_missing() -> None:
    """Bản ghi cũ không có `raw_create_response`. Trả None chứ không dựng câu sai."""
    resp = PaymentIntentResponse.from_model(_row(raw_create_response=None))

    assert resp.payment_link.instructions is None
    assert resp.payment_link.type == "bank_transfer_instruction"


def test_instructions_read_the_stored_account_not_the_current_one() -> None:
    """Số tài khoản phải là số LÚC TẠO ĐƠN, không phải số đang cấu hình hôm nay."""
    resp = PaymentIntentResponse.from_model(
        _row(
            raw_create_response={"bank": "VCB", "account_number": "999", "order_code": "SDOLD00001"}
        )
    )

    assert "999" in resp.payment_link.instructions
    assert "VCB" in resp.payment_link.instructions


@pytest.mark.parametrize("provider", ["momo", "zalopay"])
def test_redirect_gateways_keep_their_existing_shape(provider: str) -> None:
    """Bản vá này KHÔNG được đổi hành vi của hai cổng đang chạy thật."""
    resp = PaymentIntentResponse.from_model(
        _row(provider=provider, deeplink=f"{provider}://pay?x=1")
    )

    assert resp.payment_link.type == "checkout_url"
    assert resp.payment_link.instructions == f"{provider}://pay?x=1"
