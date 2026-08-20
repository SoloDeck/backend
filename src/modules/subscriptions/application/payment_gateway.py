"""Port for external payment-provider adapters.

Per AGENTS.md, subscriptions "does NOT own payment gateway processing... we
store outcomes only" — concrete implementations live under src/integrations/.
"""

from decimal import Decimal
from typing import Any, NamedTuple, Protocol

from src.shared.exceptions.domain import DomainError


class PaymentGatewayError(DomainError):
    """The provider rejected the request or could not be reached.

    Lives on the PORT, not inside one adapter: every gateway implementation
    raises it, and the module that catches it must not have to import from
    `integrations/momo/` to name the exception it is catching.
    """

    def __init__(self, message: str = "Payment provider request failed") -> None:
        super().__init__(message)


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
    # Số tiền provider BÁO ĐÃ THU. Để đối chiếu với số tiền ta yêu cầu — lệch nhau là bất
    # thường, phải có người xem. `None` khi provider không gửi hoặc không đọc được.
    amount: Decimal | None = None


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
        configured default when omitted. The resolved redirect target must
        never equal `notify_url` (the server-to-server callback, which is not
        browser-reachable) — implementations should raise if it would."""
        ...

    def verify_callback_signature(self, payload: dict[str, Any]) -> bool: ...

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult: ...

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        """Response body the provider's server expects back from our webhook."""
        ...
