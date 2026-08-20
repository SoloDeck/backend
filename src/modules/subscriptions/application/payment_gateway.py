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


class QueryResult(NamedTuple):
    """Kết quả hỏi THẲNG nhà cung cấp: "đơn này trả tiền chưa?"

    Vì sao cần: cả hệ thống chỉ có MỘT cách biết khách đã trả tiền — ngồi chờ webhook.
    Mất cú gọi đó là mất vĩnh viễn: đơn nằm `pending`, khách bị trừ tiền mà không được
    gói, và không một job nào đi kiểm lại. Chuyện này đã xảy ra thật trên staging
    (20/08/2026): app MoMo UAT trừ tiền thành công nhưng IPN không bao giờ tới.

    CỐ Ý KHÔNG đưa vào `PaymentGateway` Protocol: thêm vào đó là bắt MỌI cổng phải cài
    đặt, kể cả những cổng đang làm dở ở nhánh khác. Chỗ gọi dùng `hasattr` để cổng nào
    có thì hỏi, không có thì bỏ qua — không cổng nào bị buộc phải đổi.  #Huynh
    """

    # True = nhà cung cấp XÁC NHẬN đã thu tiền. Mọi giá trị khác (chưa trả, đơn không
    # tồn tại, đã huỷ) đều là False — KHÔNG phải lỗi, chỉ là "chưa".
    paid: bool
    # Mã nhà cung cấp trả về, giữ nguyên để ghi log và soi khi cần.
    result_code: Any
    # Số tiền nhà cung cấp BÁO ĐÃ THU, để đối chiếu y như nhánh webhook.
    amount: Decimal | None
    provider_reference: str | None
    message: str
    raw: dict[str, Any]


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
