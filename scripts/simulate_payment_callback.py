#!/usr/bin/env python
"""Simulate a MoMo IPN callback against a locally running SoloDesk API.

Useful when developing against the real MoMo sandbox but the machine has no
public IP/tunnel for MoMo's servers to reach `momo_ipn_url` directly — this
builds a payload signed the same way MoMo's real IPN would be (same keys as
whatever `MOMO_*` settings are configured) and POSTs it to our webhook
endpoint, exactly as MoMo's server would.

Usage:
    python scripts/simulate_payment_callback.py --order-id <payment id> --amount 199000 \
        [--outcome success|fail]
"""

import argparse
import sys
from pathlib import Path

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from src.shared.dependencies.payments import get_momo_client


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-id", required=True, help="Payment intent id (== MoMo orderId)")
    parser.add_argument("--amount", required=True, type=int, help="Amount in whole VND")
    parser.add_argument("--outcome", choices=["success", "fail"], default="success")
    parser.add_argument(
        "--base-url", default="http://localhost:8000/api/v1", help="SoloDesk API base URL"
    )
    args = parser.parse_args()

    client = get_momo_client()
    if args.outcome == "success":
        payload = client.sign_ipn(order_id=args.order_id, amount=args.amount)
    else:
        payload = client.sign_ipn(
            order_id=args.order_id, amount=args.amount, result_code=1, message="Payment failed"
        )

    response = httpx.post(f"{args.base_url}/payments/webhooks/momo", json=payload, timeout=10)
    print(f"POST /payments/webhooks/momo -> {response.status_code}")
    print(response.json())


if __name__ == "__main__":
    main()
