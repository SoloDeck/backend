"""Payment provider webhook callbacks — no authentication.

A provider's server (real or, here, our mock simulate script) can't present a
SoloDesk JWT. The request body is the provider's raw native payload, not the
contract's generic PaymentWebhookRequest envelope — a real provider's server
sends its own documented fields and can't be made to wrap them for us.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.payments.schemas import PaymentWebhookAcceptedResponse
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import PaymentProvider
from src.shared.dependencies.payments import MomoClientDep
from src.shared.exceptions.domain import DomainError
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]

_PAYMENT_RESULT_DEEP_LINK = "solodesk://payment-result"


@router.post(
    "/{provider}", response_model=ApiResponse[PaymentWebhookAcceptedResponse], status_code=202
)
async def receive_payment_webhook(
    provider: str,
    payload: dict[str, Any],
    db: DBSession,
    momo_client: MomoClientDep,
) -> ApiResponse[PaymentWebhookAcceptedResponse]:
    try:
        provider_enum = PaymentProvider(provider)
    except ValueError as exc:
        raise DomainError(f"Unsupported payment provider '{provider}'") from exc

    await SubscriptionsService(db=db, momo_client=momo_client).handle_payment_callback(
        provider_enum, payload
    )
    event_id = str(payload.get("orderId", ""))
    return ApiResponse.ok(PaymentWebhookAcceptedResponse(accepted=True, event_id=event_id), code=202)


@router.get("/momo/result", include_in_schema=False)
async def momo_payment_result_landing(resultCode: str | None = None) -> HTMLResponse:
    """GET landing page MoMo's browser redirects to after checkout (success or
    cancel) — NOT the IPN webhook above, which stays POST-only. Best-effort
    hands off to the mobile app via a custom-scheme deep link; the app's own
    background polling (not this page) is the authoritative source of the
    actual payment result."""
    is_success = resultCode == "0"
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
