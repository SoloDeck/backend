"""Port for external payment-provider adapters.

Per AGENTS.md, subscriptions "does NOT own payment gateway processing... we
store outcomes only" — concrete implementations live under src/integrations/.
"""

from collections.abc import Mapping
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
    # False = su kien nay KHONG lien quan toi bat ky don nao cua ta; ack roi thoi.
    #
    # Can mot co RIENG chu khong suy tu `success=False`: hai chuyen khac han nhau.
    # `success=False` la "co don, va no HONG" (thu thieu tien, sai chu ky) — phai ghi vao
    # don do. Con day la "day khong phai viec cua ta": SePay ban webhook cho MOI bien dong
    # so du, ke ca nhung khoan CHUYEN DI do chinh chu tai khoan thuc hien. Bat chung phai
    # ung voi mot don nao do se cho ra 404, va SePay se gui lai mai mai mot su kien khong
    # bao gio co the khop.
    actionable: bool = True


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
        order_code: str | None = None,
    ) -> CreatePaymentResult:
        """`order_code` là mã đơn NGẮN (vd `SD7K2M9PQR`), khác `order_id` (UUID).

        MoMo/ZaloPay bỏ qua nó: hai cổng đó nhận mã đơn do ta gửi và trả lại nguyên vẹn.
        Cổng kiểu đối soát ngân hàng thì chỉ có dòng nội dung chuyển khoản để nhận ra đơn,
        mà 32 ký tự hex không sống sót qua việc bị cắt ngắn và gõ tay.

        `redirect_url`, if given, is where the provider sends the browser
        after payment — per-checkout. Falls back to the gateway's own
        configured default when omitted. The resolved redirect target must
        never equal `notify_url` (the server-to-server callback, which is not
        browser-reachable) — implementations should raise if it would."""
        ...

    def verify_callback_signature(
        self, payload: dict[str, Any], headers: Mapping[str, str] | None = None
    ) -> bool:
        """Xác thực callback. `headers` là header HTTP của chính request webhook đó.

        MoMo và ZaloPay ký ngay TRONG thân request, nên hai adapter đó bỏ qua `headers`.
        Cổng kiểu đối soát ngân hàng (SePay) thì không có gì để ký trong thân — thứ chứng
        minh danh tính nằm ở header `Authorization`. Không có tham số này thì adapter loại
        đó buộc phải tin bất kỳ ai POST đúng hình dạng JSON.

        `None` nghĩa là "phía gọi không truyền header xuống", KHÔNG phải "không có header".
        Adapter nào cần header thì phải NÉM lỗi rõ ràng ở ca đó chứ đừng lặng lẽ trả
        `False`: trả False biến một lỗi đi dây thành "mọi thanh toán thật đều sai chữ ký",
        một triệu chứng không chỉ được về nguyên nhân.
        """
        ...

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult: ...

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        """Response body the provider's server expects back from our webhook."""
        ...
