"""Port for external payment-provider adapters.

Per AGENTS.md, subscriptions "does NOT own payment gateway processing... we
store outcomes only" — concrete implementations live under src/integrations/.
"""

from decimal import Decimal
from typing import Any, NamedTuple, Protocol


class CreatePaymentResult(NamedTuple):
    pay_url: str | None
    deeplink: str | None
    qr_code_url: str | None
    raw: dict[str, Any]


class CallbackResult(NamedTuple):
    order_id: str
    provider_reference: str | None
    success: bool
    message: str


class PaymentGateway(Protocol):
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
        """`redirect_url`, if given, is where the provider sends the browser
        after payment — per-checkout. Falls back to the gateway's own
        configured default when omitted."""
        ...

    def verify_callback_signature(self, payload: dict[str, Any]) -> bool: ...

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult: ...

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        """Response body the provider's server expects back from our webhook."""
        ...
