"""SePay client — https://docs.sepay.vn/tich-hop-webhooks.html

SePay KHÔNG phải cổng thanh toán theo nghĩa MoMo/ZaloPay. Nó không giữ tiền và không có
API "tạo đơn": tiền chảy thẳng vào tài khoản ngân hàng của chính ta, còn SePay chỉ đọc
biến động số dư rồi bắn webhook. Ba hệ quả, và cả ba đều khác adapter bên cạnh:

1. `create_payment` KHÔNG gọi mạng. Nó chỉ dựng một URL ảnh VietQR. Không có đường nào
   "không kết nối được tới SePay" lúc checkout, vì lúc checkout ta không gọi SePay.
2. Xác thực callback nằm ở HEADER, không phải trong thân. SePay gửi
   ``Authorization: Apikey <API_KEY>``. Không có gì trong thân request để ký cả — đó là
   lý do protocol `PaymentGateway` phải nhận thêm `headers`.
3. Không có "callback thất bại". Một khoản tiền vào là một khoản tiền vào; đơn không ai
   trả thì đơn giản là không có webhook, và `_expire_if_overdue` bên service dọn nó.

Điểm nối duy nhất giữa một khoản tiền vào và một đơn hàng là MÃ ĐƠN trong nội dung
chuyển khoản (`order_code`, dạng ``SD7K2M9PQR`` — xem `generate_order_code`). Đó là một
sợi dây mỏng hơn hẳn chữ ký HMAC: người dùng gõ tay được, ngân hàng cắt ngắn được. Vì
vậy `parse_callback` đọc mã theo hai đường (trường `code` SePay đã tách sẵn, rồi mới dò
trong `content`), và service vẫn đối chiếu số tiền trước khi kích hoạt gói.
"""

import hmac
import re
import urllib.parse
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from src.modules.subscriptions.application.payment_gateway import (
    CallbackResult,
    CreatePaymentResult,
    PaymentGatewayError,
)
from src.modules.subscriptions.domain.entities.subscription_payment import (
    ORDER_CODE_BODY_LENGTH,
    ORDER_CODE_PREFIX,
)

log = structlog.get_logger(__name__)

__all__ = [
    "SEPAY_MAX_AMOUNT_VND",
    "SEPAY_MIN_AMOUNT_VND",
    "MockSePayClient",
    "PaymentGatewayError",
    "SePayClient",
]

# Tiền tố header SePay dùng. Nguyên văn: `Authorization: Apikey API_KEY_CUA_BAN`.
# Chữ "Apikey" viết hoa chữ A, phần còn lại thường — nhưng ta so KHÔNG phân biệt hoa
# thường ở tiền tố, vì proxy và framework hay chuẩn hoá lại scheme của Authorization.
_AUTH_SCHEME = "apikey"

# Chỉ nhận tiền VÀO. `transferType` = "out" là một khoản CHUYỂN ĐI — nếu nó lọt qua đây
# thì một lần ta trả tiền cho người khác sẽ được ghi nhận là khách đã thanh toán.
_TRANSFER_TYPE_IN = "in"

# Dò mã đơn trong nội dung chuyển khoản khi SePay không tách sẵn vào trường `code`.
# Bảng chữ phải khớp `_ORDER_CODE_ALPHABET` (Crockford base32: không I, L, O, U).
_ORDER_CODE_RE = re.compile(rf"{ORDER_CODE_PREFIX}[0-9A-HJKMNP-TV-Z]{{{ORDER_CODE_BODY_LENGTH}}}")

# Cận dưới là mức chuyển khoản tối thiểu trên app ngân hàng. Cận trên để bằng hai cổng
# kia cho nhất quán — hạn mức THẬT là hạn mức tài khoản của chủ tài khoản, không phải
# hằng số công khai, nên hai giá trị này nằm ở Settings để chỉnh bằng env.
SEPAY_MIN_AMOUNT_VND = 1_000
SEPAY_MAX_AMOUNT_VND = 50_000_000


def _vnd(amount: Decimal | int) -> str:
    """``50000000`` → ``"50.000.000"`` — cho câu báo trước mặt người dùng."""
    return f"{int(amount):,}".replace(",", ".")


def _parse_amount(amount: Any) -> Decimal | None:
    """Số tiền SePay báo đã vào tài khoản. ``None`` khi thiếu hoặc không đọc được.

    Qua ``str()`` chứ không ``Decimal(float)``: dựng Decimal từ float kéo theo sai số nhị
    phân, mà đây là TIỀN.
    """
    if amount is None:
        return None
    try:
        return Decimal(str(amount).strip())
    except (TypeError, ValueError, InvalidOperation):
        return None


def extract_order_code(payload: Mapping[str, Any]) -> str:
    """Mã đơn đọc ra từ một webhook SePay. Chuỗi rỗng khi không tìm thấy.

    Hai đường, theo thứ tự:

    1. Trường ``code`` — SePay đã tự tách mã theo quy tắc cấu hình ở dashboard. Tin đường
       này trước vì nó là thứ SePay bảo đảm.
    2. Dò trong ``content`` (nội dung chuyển khoản thô). Cần đường này vì trường ``code``
       CHỈ có giá trị khi quy tắc tách ở dashboard được cấu hình đúng — mà đó là một ô
       cấu hình trên web, không phải thứ code này kiểm soát được. Cấu hình sai thì
       ``code`` về ``null`` và mọi khoản tiền vào thành mồ côi, trong khi mã vẫn nằm y
       nguyên trong ``content``.

    Chuẩn hoá về chữ hoa: một số ngân hàng viết thường hoá nội dung chuyển khoản.
    """
    code = str(payload.get("code") or "").strip().upper()
    if _ORDER_CODE_RE.fullmatch(code):
        return code
    match = _ORDER_CODE_RE.search(str(payload.get("content") or "").upper())
    return match.group(0) if match else ""


class _SePayShared:
    """Phần dùng chung cho client thật và bản mock."""

    webhook_api_key: str
    bank_code: str
    account_number: str
    qr_base_url: str
    min_amount: int = SEPAY_MIN_AMOUNT_VND
    max_amount: int = SEPAY_MAX_AMOUNT_VND

    # Hai helper dưới nằm ở LỚP CHUNG chứ không riêng bản mock, đúng như `sign_ipn` bên
    # MoMo và `sign_callback` bên ZaloPay. Lý do: `scripts/simulate_payment_callback.py`
    # dựng payload từ client THẬT do DI trả về, để số tài khoản và API key trong payload
    # giả đúng bằng cấu hình đang chạy. Để riêng ở mock thì script chết bằng AttributeError.

    def build_webhook_payload(
        self,
        *,
        order_code: str,
        amount: Decimal | int,
        transfer_type: str = "in",
        include_code_field: bool = True,
        reference_code: str = "FT26082012345678",
        transaction_id: int = 92704,
    ) -> dict[str, Any]:
        """Dựng một webhook SePay đúng hình dạng thật — cho test và script mô phỏng.

        `include_code_field=False` mô phỏng ca quy tắc tách mã ở dashboard chưa được cấu
        hình: SePay trả ``code: null`` và mã đơn chỉ còn nằm trong ``content``.
        """
        return {
            "id": transaction_id,
            "gateway": self.bank_code,
            "transactionDate": "2026-08-20 11:08:33",
            "accountNumber": self.account_number,
            "subAccount": None,
            "code": order_code if include_code_field else None,
            "content": f"{order_code} chuyen tien",
            "transferType": transfer_type,
            "description": f"NGUYEN VAN A chuyen tien {order_code}",
            "transferAmount": int(amount),
            "accumulated": 105_000_000,
            "referenceCode": reference_code,
        }

    def auth_headers(self) -> dict[str, str]:
        """Header xác thực đúng như SePay gửi — tiện cho test."""
        return {"Authorization": f"Apikey {self.webhook_api_key}"}

    def _to_whole_vnd(self, amount: Decimal, currency: str) -> int:
        """Chuyển khoản ngân hàng chỉ có VND, số nguyên, và trong hạn mức.

        Chốt chặn này KHÔNG bảo vệ một lời gọi mạng như bên MoMo/ZaloPay (ở đây không có
        lời gọi nào). Nó chặn việc dựng ra một mã QR yêu cầu số tiền mà ngân hàng sẽ từ
        chối — người dùng quét QR rồi mới thấy hỏng, và không có gì nói cho họ vì sao.
        """
        if currency != "VND":
            raise PaymentGatewayError(
                f"Chuyển khoản ngân hàng chỉ nhận VND, gói này đang để '{currency}'. "
                f"Bạn liên hệ quản trị viên để chỉnh lại gói giúp mình nhé."
            )
        if amount != amount.to_integral_value():
            raise PaymentGatewayError(
                f"Chuyển khoản ngân hàng chỉ nhận số tiền chẵn, gói này là {amount}."
            )
        value = int(amount)
        if not self.min_amount <= value <= self.max_amount:
            raise PaymentGatewayError(
                f"Chuyển khoản chỉ nhận số tiền từ {_vnd(self.min_amount)}đ đến "
                f"{_vnd(self.max_amount)}đ cho một giao dịch — gói này đang để "
                f"{_vnd(value)}đ nên không thanh toán được. Bạn liên hệ quản trị viên "
                f"để chỉnh lại giá gói giúp mình nhé."
            )
        return value

    def _build_qr_url(self, *, amount: int, order_code: str) -> str:
        """URL ảnh VietQR động — https://docs.sepay.vn/tao-qr-code-vietqr-dong.html

        ``des`` (nội dung chuyển khoản) là ĐÚNG mã đơn, không thêm chữ nào khác. Thêm chữ
        vào đó chỉ làm quy tắc tách mã ở dashboard mong manh hơn, và tài liệu VietQR nói
        rõ trường này "chỉ nhập chữ, số, không dấu" — mã đơn vốn đã chỉ có A-Z0-9.
        """
        query = urllib.parse.urlencode(
            {
                "acc": self.account_number,
                "bank": self.bank_code,
                "amount": amount,
                "des": order_code,
            }
        )
        return f"{self.qr_base_url}?{query}"

    def _require_order_code(self, order_code: str | None) -> str:
        """SePay là cổng DUY NHẤT bắt buộc phải có `order_code`.

        MoMo/ZaloPay nhận UUID của đơn và trả lại nguyên vẹn, nên chúng bỏ qua tham số
        này. Ở đây mã đơn LÀ toàn bộ sợi dây nối khoản tiền vào với đơn hàng — thiếu nó
        thì mã QR sinh ra vẫn quét được, tiền vẫn vào tài khoản, và KHÔNG BAO GIỜ khớp
        được với đơn nào. Chết ồn ào ở đây tốt hơn nhiều so với một khoản tiền mồ côi.
        """
        if not order_code:
            raise PaymentGatewayError(
                "SePay checkout requires an order_code — without it an incoming "
                "transfer cannot be matched back to this payment."
            )
        return order_code

    def verify_callback_signature(
        self, payload: dict[str, Any], headers: Mapping[str, str] | None = None
    ) -> bool:
        """SePay gửi ``Authorization: Apikey <API_KEY>``. Không có gì ký trong thân.

        `headers is None` nghĩa là phía gọi QUÊN truyền header xuống, chứ không phải
        request không có header. Ném lỗi rõ ràng thay vì trả `False`: trả `False` biến một
        lỗi đi dây thành "mọi thanh toán thật đều sai xác thực" — một triệu chứng không
        chỉ được về nguyên nhân. Xem docstring của `PaymentGateway.verify_callback_signature`.

        So sánh bằng `hmac.compare_digest`: khoá này là bí mật dùng lại cho mọi request,
        nên so bằng `==` để lộ độ dài tiền tố khớp qua thời gian chạy.
        """
        if headers is None:
            raise PaymentGatewayError(
                "SePay callback verification needs the request headers — the caller did "
                "not pass them (see PaymentGateway.verify_callback_signature)."
            )
        if not self.webhook_api_key:
            raise PaymentGatewayError(
                "SEPAY_WEBHOOK_API_KEY is not configured — refusing to accept an "
                "unauthenticated payment callback."
            )
        raw = str(headers.get("authorization") or headers.get("Authorization") or "").strip()
        scheme, _, presented = raw.partition(" ")
        if scheme.lower() != _AUTH_SCHEME:
            return False
        return hmac.compare_digest(presented.strip(), self.webhook_api_key)

    def parse_callback(self, payload: dict[str, Any]) -> CallbackResult:
        """Webhook đã xác thực → `CallbackResult`.

        `success=False` ở hai ca, và cả hai đều KHÔNG phải "thanh toán thất bại":

        - `transferType` không phải "in": đây là tiền CHUYỂN ĐI. Bỏ kiểm này thì mỗi lần
          chủ tài khoản trả tiền cho ai đó, hệ thống lại ghi nhận một đơn được thanh toán.
        - Không tìm ra mã đơn: một khoản tiền vào không thuộc về đơn nào (khách chuyển
          nhầm, gõ sai mã, hoặc quy tắc tách mã ở dashboard bị sai). Tiền đã vào tài khoản
          thật, nên phải ghi nhận để có người xử tay chứ không được lặng lẽ nuốt.
        """
        transfer_type = str(payload.get("transferType") or "").strip().lower()
        if transfer_type != _TRANSFER_TYPE_IN:
            return CallbackResult(
                order_id="",
                provider_reference=str(payload.get("referenceCode") or "") or None,
                success=False,
                message=f"Bỏ qua giao dịch không phải tiền vào (transferType={transfer_type!r}).",
                amount=None,
                actionable=False,
            )

        order_code = extract_order_code(payload)
        reference = str(payload.get("referenceCode") or payload.get("id") or "") or None
        if not order_code:
            return CallbackResult(
                order_id="",
                provider_reference=reference,
                success=False,
                message="Không tìm thấy mã đơn trong nội dung chuyển khoản.",
                amount=_parse_amount(payload.get("transferAmount")),
            )

        return CallbackResult(
            order_id=order_code,
            provider_reference=reference,
            success=True,
            message="Success",
            amount=_parse_amount(payload.get("transferAmount")),
        )

    def build_ack_response(self, result: CallbackResult) -> dict[str, Any]:
        """Thân phản hồi SePay chờ nhận — ``{"success": true}`` kèm HTTP 200/201.

        Tài liệu nói rõ hai điều kiện đó, và 202 KHÔNG nằm trong danh sách. Route webhook
        chung trả 202 kèm envelope `ApiResponse`, nên nếu SePay đi qua đúng route mặc định
        đó thì mọi callback đều bị coi là chưa nhận và SePay gửi lại mãi. Xem
        `payments/api/public_router.py` — chỗ đó có nhánh riêng cho SePay.
        """
        return {"success": True}


class SePayClient(_SePayShared):
    """Client SePay thật. Hiện thực protocol `PaymentGateway`.

    "Thật" ở đây không có nghĩa là gọi mạng: luồng checkout của SePay hoàn toàn cục bộ
    (dựng URL VietQR). Khác biệt duy nhất với bản mock là nó dùng số tài khoản và khoá
    thật lấy từ Settings.
    """

    def __init__(
        self,
        *,
        webhook_api_key: str,
        bank_code: str,
        account_number: str,
        qr_base_url: str,
        min_amount: int = SEPAY_MIN_AMOUNT_VND,
        max_amount: int = SEPAY_MAX_AMOUNT_VND,
    ) -> None:
        self.webhook_api_key = webhook_api_key
        self.bank_code = bank_code
        self.account_number = account_number
        self.qr_base_url = qr_base_url
        self.min_amount = min_amount
        self.max_amount = max_amount

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
        """Dựng mã QR chuyển khoản. KHÔNG gọi mạng.

        `notify_url` và `redirect_url` không dùng tới: webhook được cấu hình MỘT LẦN trên
        dashboard SePay chứ không gửi kèm từng đơn, và chuyển khoản ngân hàng không có
        bước "quay lại trang web" nào để redirect. Hai tham số có mặt để khớp protocol.
        """
        if not self.account_number or not self.bank_code:
            raise PaymentGatewayError(
                "SEPAY_ACCOUNT_NUMBER / SEPAY_BANK_CODE chưa được cấu hình, chưa tạo được "
                "mã QR chuyển khoản. Bạn liên hệ quản trị viên giúp mình nhé."
            )
        code = self._require_order_code(order_code)
        amount_int = self._to_whole_vnd(amount, currency)
        qr_url = self._build_qr_url(amount=amount_int, order_code=code)

        log.info(
            "sepay.create_payment",
            order_id=order_id,
            order_code=code,
            amount=amount_int,
            bank=self.bank_code,
        )
        return CreatePaymentResult(
            pay_url=qr_url,
            # Chuyển khoản ngân hàng không có deeplink mở app nào để trỏ tới.
            deeplink=None,
            qr_code_url=qr_url,
            raw={
                "order_code": code,
                "amount": amount_int,
                "bank": self.bank_code,
                "account_number": self.account_number,
                "qr_url": qr_url,
            },
        )


# Chỉ dùng cho dev/test — không bao giờ là số tài khoản thật.
_MOCK_API_KEY = "mock-sepay-webhook-key-dev-only"
_MOCK_BANK_CODE = "OCB"
_MOCK_ACCOUNT_NUMBER = "0000000000"
_MOCK_QR_BASE_URL = "https://mock-payment.solodesk.dev/sepay/qr"


class MockSePayClient(_SePayShared):
    """Bản đứng thay offline cho `SePayClient` — cho test và dev local.

    Dùng chung toàn bộ phần xác thực và phân tích callback với client thật (chúng nằm ở
    `_SePayShared`), nên vòng ký–kiểm ở đây là thật; chỉ số tài khoản và khoá là giả.
    """

    webhook_api_key = _MOCK_API_KEY
    bank_code = _MOCK_BANK_CODE
    account_number = _MOCK_ACCOUNT_NUMBER
    qr_base_url = _MOCK_QR_BASE_URL

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
        code = self._require_order_code(order_code)
        amount_int = self._to_whole_vnd(amount, currency)
        qr_url = self._build_qr_url(amount=amount_int, order_code=code)
        return CreatePaymentResult(
            pay_url=qr_url,
            deeplink=None,
            qr_code_url=qr_url,
            raw={
                "order_code": code,
                "amount": amount_int,
                "bank": self.bank_code,
                "account_number": self.account_number,
                "qr_url": qr_url,
            },
        )
