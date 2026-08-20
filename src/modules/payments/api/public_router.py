"""Payment provider webhook callbacks — no authentication.

A provider's server (real or, here, our mock simulate script) can't present a
SoloDesk JWT. The request body is the provider's raw native payload, not the
contract's generic PaymentWebhookRequest envelope — a real provider's server
sends its own documented fields and can't be made to wrap them for us.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.integrations.sepay.client import extract_order_code
from src.modules.payments.schemas import PaymentWebhookAcceptedResponse
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import PaymentProvider
from src.shared.dependencies.payments import (
    MomoClientDep,
    SePayClientDep,
    ZaloPayClientDep,
)
from src.shared.exceptions.domain import DomainError
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]

_PAYMENT_RESULT_DEEP_LINK = "solodesk://payment-result"


def _event_id(provider: PaymentProvider, payload: dict[str, Any]) -> str:
    """Mã đơn để trả lại trong `event_id` — mỗi cổng cất nó ở một chỗ khác nhau.

    MoMo để `orderId` ngay ở cấp cao nhất. ZaloPay bọc mọi thứ trong `data` dưới dạng
    một CHUỖI JSON, nên `payload.get("orderId")` với ZaloPay luôn ra rỗng — không phải
    lỗi chết người (đây chỉ là trường phản hồi), nhưng nó làm mọi log và mọi lần dò lại
    webhook ZaloPay đều trống trơn đúng cái cột cần nhất.

    Chỉ đọc để báo lại; không tin vào nó cho bất kỳ quyết định nghiệp vụ nào — phần đó
    đã đi qua kiểm chữ ký trong service rồi.
    """
    if provider is PaymentProvider.ZALOPAY:
        try:
            data = json.loads(payload.get("data") or "{}")
        except ValueError:
            return ""
        return str(data.get("app_trans_id", "")) if isinstance(data, dict) else ""
    if provider is PaymentProvider.SEPAY:
        # SePay khong co "orderId" — moi noi voi don hang la ma don trong noi dung
        # chuyen khoan. Dung dung mot ham voi adapter de hai cho khong the lech nhau.
        return extract_order_code(payload)
    return str(payload.get("orderId", ""))


@router.post(
    "/{provider}", response_model=ApiResponse[PaymentWebhookAcceptedResponse], status_code=202
)
async def receive_payment_webhook(
    provider: str,
    payload: dict[str, Any],
    request: Request,
    db: DBSession,
    momo_client: MomoClientDep,
    zalopay_client: ZaloPayClientDep,
    sepay_client: SePayClientDep,
) -> ApiResponse[PaymentWebhookAcceptedResponse] | JSONResponse:
    try:
        provider_enum = PaymentProvider(provider)
    except ValueError as exc:
        raise DomainError(f"Unsupported payment provider '{provider}'") from exc

    # `request.headers` phải đi cùng payload xuống tận adapter. MoMo/ZaloPay ký trong
    # thân nên không cần, nhưng cổng đối soát ngân hàng chứng minh danh tính bằng header
    # `Authorization` — quên truyền là adapter đó không còn gì để xác thực.
    ack = await SubscriptionsService(
        db=db,
        momo_client=momo_client,
        zalopay_client=zalopay_client,
        sepay_client=sepay_client,
    ).handle_payment_callback(provider_enum, payload, request.headers)

    # HAI cổng đòi đúng thân phản hồi của riêng chúng kèm mã 200, và `build_ack_response`
    # của mỗi adapter dựng sẵn đúng thân đó:
    #
    #   SePay   → {"success": true}
    #             docs.sepay.vn/tich-hop-webhooks.html
    #   ZaloPay → {"return_code": 1, "return_message": "success"}
    #             docs.zalopay.vn/docs/developer-tools/knowledge-base/callback/
    #
    # Cả hai coi "không thấy thứ mình đòi" là CHƯA NHẬN rồi giao lại — ZaloPay ghi thẳng
    # `result['return_code'] = 0  # callback again (up to 3 times)`. Bao bì `ApiResponse`
    # kèm 202 không chứa trường nào trong số đó, nên trước bản vá này callback của cả hai
    # cổng đều bị giao lại, trong khi `build_ack_response` vẫn dựng sẵn thân đúng mà không
    # ai gọi tới.
    #
    # Gói VẪN kích hoạt ngay từ lần giao đầu (handler commit trước khi đáp, và idempotent),
    # nên không mất tiền. Cái hỏng nằm ở phía cổng: đơn hiện ra như chưa từng được xác nhận.
    #
    # MoMo KHÔNG đổi. Tài liệu AIOv2 không nói rõ nó chờ thân phản hồi nào, mà đổi hình dạng
    # phản hồi của một cổng đang chạy thật dựa trên phỏng đoán thì rủi ro hơn hẳn cái được.
    if provider_enum in {PaymentProvider.SEPAY, PaymentProvider.ZALOPAY}:
        return JSONResponse(ack, status_code=200)

    event_id = _event_id(provider_enum, payload)
    return ApiResponse.ok(
        PaymentWebhookAcceptedResponse(accepted=True, event_id=event_id), code=202
    )


@router.get("/momo/result", include_in_schema=False)
async def momo_payment_result_landing(resultCode: str | None = None) -> HTMLResponse:
    """GET landing page MoMo's browser redirects to after checkout (success or
    cancel) — NOT the IPN webhook above, which stays POST-only. Best-effort
    hands off to the mobile app via a custom-scheme deep link; the app's own
    background polling (not this page) is the authoritative source of the
    actual payment result."""
    return _result_landing(resultCode == "0")


@router.get("/zalopay/result", include_in_schema=False)
async def zalopay_payment_result_landing(status: str | None = None) -> HTMLResponse:
    """Trang GET trình duyệt rơi về sau khi rời cổng ZaloPay — KHÔNG phải webhook.

    ZaloPay báo kết quả bằng `status` = 1 (MoMo dùng `resultCode` = 0 — hai cổng ngược
    nhau cả tên tham số lẫn giá trị "thành công", nên đừng chép qua lại).

    Trang này chỉ để nói một câu cho người dùng rồi đẩy về app; nó KHÔNG được coi là
    nguồn sự thật. Query string ở đây do trình duyệt mang tới nên ai cũng sửa được —
    sự thật nằm ở callback đã kiểm chữ ký, hoặc ở `/v2/query` hỏi thẳng ZaloPay.
    """
    return _result_landing(status == "1")


def _result_landing(is_success: bool) -> HTMLResponse:
    heading = "Thanh toán thành công" if is_success else "Đã đóng phiên thanh toán"
    body = (
        "Bạn có thể quay lại ứng dụng SoloDesk."
        if is_success
        else "Giao dịch đã được huỷ hoặc chưa hoàn tất. Bạn có thể quay lại ứng dụng SoloDesk để kiểm tra."
    )
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0;url={_PAYMENT_RESULT_DEEP_LINK}">
<title>SoloDesk</title>
</head>
<body style="font-family: sans-serif; text-align: center; padding: 48px 16px;">
<h1>{heading}</h1>
<p>{body}</p>
<p><a href="{_PAYMENT_RESULT_DEEP_LINK}">Mở lại ứng dụng SoloDesk</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)
