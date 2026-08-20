"""Gọi THẬT ra sandbox ZaloPay bằng chính `ZaloPayClient` của app.

Không phải test (test không được đi mạng — xem `tests/conftest.py`). Đây là công cụ
chạy tay để trả lời một câu mà unit test không trả lời được: chuỗi ký ta dựng có được
ZaloPay THẬT chấp nhận không, hay chỉ khớp với bản mock của chính ta.

    docker compose run --rm test python scripts/zalopay_sandbox_smoke.py

Dùng đúng credentials trong Settings — mặc định là app sandbox 2554 ZaloPay công bố
trong github.com/zalopay-samples/test-apps. Không tiêu tiền thật: đơn được tạo ra rồi
bỏ đó, không ai thanh toán.
"""

import asyncio
import json
import uuid
from decimal import Decimal

from src.config.settings import settings
from src.integrations.zalopay.client import ZaloPayClient, build_app_trans_id


async def main() -> None:
    client = ZaloPayClient(
        app_id=settings.zalopay_app_id,
        key1=settings.zalopay_key1,
        key2=settings.zalopay_key2,
        app_user=settings.zalopay_app_user,
        endpoint=settings.zalopay_endpoint,
        query_endpoint=settings.zalopay_query_endpoint,
        redirect_url=settings.zalopay_redirect_url,
        timeout_seconds=settings.zalopay_timeout_seconds,
        min_amount=settings.zalopay_min_amount,
        max_amount=settings.zalopay_max_amount,
    )

    order_id = str(uuid.uuid4())
    app_trans_id = build_app_trans_id(order_id)
    print(f"order_id     : {order_id}")
    print(f"app_trans_id : {app_trans_id} ({len(app_trans_id)} ký tự, trần là 40)")

    result = await client.create_payment(
        order_id=order_id,
        amount=Decimal("199000"),
        currency="VND",
        order_info="SoloDesk Pro plan upgrade",
        notify_url=settings.zalopay_callback_url,
    )
    print("\n--- create ---")
    print(json.dumps(result.raw, indent=2, ensure_ascii=False))
    print(f"pay_url  : {result.pay_url}")
    print(f"deeplink : {result.deeplink}")

    status = await client.query_payment_status(order_id, result.raw["app_trans_id"])
    print("\n--- query ---")
    print(json.dumps(status, indent=2, ensure_ascii=False))
    print("\nreturn_code 3 = 'chưa thực hiện' — đúng, vì chưa ai trả tiền đơn này.")


if __name__ == "__main__":
    asyncio.run(main())
