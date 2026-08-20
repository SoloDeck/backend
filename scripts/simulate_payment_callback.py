#!/usr/bin/env python
"""Simulate a payment-provider callback against a locally running SoloDesk API.

Useful when developing against a real provider sandbox but the machine has no
public IP/tunnel for the provider's servers to reach our webhook directly — this
builds a payload signed the same way the provider's real callback would be (same
keys as whatever `MOMO_*` / `ZALOPAY_*` settings are configured) and POSTs it to
our webhook endpoint, exactly as the provider's server would.

Usage:
    python scripts/simulate_payment_callback.py --order-id <payment id> --amount 199000 \
        [--provider momo|zalopay] [--outcome success|fail]

`--outcome fail` chỉ có nghĩa với MoMo. ZaloPay và SePay KHÔNG gửi callback thất bại —
đơn hỏng thì đơn giản là không có callback nào cả, và intent tự hết hạn. Chọn fail với
hai cổng đó sẽ bị từ chối ngay ở đây thay vì dựng ra một payload thực tế không tồn tại.

SePay có sẵn Test Mode trên my.sepay.vn ("+ Mô phỏng giao dịch") làm đúng việc này từ
phía họ. Script này vẫn hữu ích khi máy chưa có URL công khai để SePay gọi vào.
"""

import argparse
import sys
from pathlib import Path

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from src.shared.dependencies.payments import (
    get_momo_client,
    get_sepay_client,
    get_zalopay_client,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", required=True, help="Payment intent id")
    parser.add_argument("--amount", required=True, type=int, help="Amount in whole VND")
    parser.add_argument("--provider", choices=["momo", "zalopay", "sepay"], default="momo")
    parser.add_argument("--outcome", choices=["success", "fail"], default="success")
    parser.add_argument(
        "--base-url", default="http://localhost:8000/api/v1", help="SoloDesk API base URL"
    )
    args = parser.parse_args()

    headers: dict[str, str] = {}
    if args.provider in {"zalopay", "sepay"} and args.outcome == "fail":
        parser.error(
            f"{args.provider} không có callback thất bại — đơn hỏng thì không có "
            f"callback nào cả. Muốn thử nhánh thất bại thì dùng --provider momo."
        )

    if args.provider == "sepay":
        client = get_sepay_client()
        payload = client.build_webhook_payload(order_code=args.order_id, amount=args.amount)
        # SePay xác thực bằng HEADER, không ký trong thân. Thiếu header này thì webhook
        # bị từ chối — và đó chính là hành vi đúng, nên script phải gửi kèm.
        headers = client.auth_headers()
    elif args.provider == "zalopay":
        payload = get_zalopay_client().sign_callback(order_id=args.order_id, amount=args.amount)
    else:
        client = get_momo_client()
        if args.outcome == "success":
            payload = client.sign_ipn(order_id=args.order_id, amount=args.amount)
        else:
            payload = client.sign_ipn(
                order_id=args.order_id, amount=args.amount, result_code=1, message="Payment failed"
            )

    path = f"/payments/webhooks/{args.provider}"
    response = httpx.post(f"{args.base_url}{path}", json=payload, headers=headers, timeout=10)
    print(f"POST {path} -> {response.status_code}")
    print(response.json())


if __name__ == "__main__":
    main()
