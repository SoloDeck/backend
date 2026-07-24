"""Zalo OA API: kết nối OAuth (connect-url + callback), trạng thái, ngắt, webhook."""

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.database.session import get_db_session
from src.integrations.zalo.client import verify_zalo_signature
from src.modules.zalo.application.service import ZaloService
from src.modules.zalo.schemas.response import ZaloConnectUrlResponse, ZaloStatusResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

log = structlog.get_logger(__name__)
router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/connect-url", response_model=ApiResponse[ZaloConnectUrlResponse])
async def get_connect_url(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ZaloConnectUrlResponse]:
    """URL để FE mở cho freelancer cấp quyền OA (ở chế độ mock trỏ thẳng về callback)."""
    url = await ZaloService(db=db).build_connect_url(user_id)
    return ApiResponse.ok(ZaloConnectUrlResponse(url=url))


@router.get("/callback", include_in_schema=False)
async def oauth_callback(code: str, state: str, db: DBSession) -> RedirectResponse:
    """Zalo chuyển hướng TRÌNH DUYỆT về đây sau khi cấp quyền — không có bearer token, danh
    tính nằm trong `state`. Xong thì đưa người dùng về trang Cài đặt của FE kèm cờ kết quả."""
    target = f"{settings.frontend_url.rstrip('/')}/settings"
    try:
        await ZaloService(db=db).complete_connection(code=code, state=state)
        return RedirectResponse(url=f"{target}?zalo=connected", status_code=303)
    except Exception as exc:  # noqa: BLE001 — mọi lỗi đều đưa người dùng về FE, không phun 500
        log.warning("zalo.callback_failed", error=str(exc))
        return RedirectResponse(url=f"{target}?zalo=error", status_code=303)


@router.get("/status", response_model=ApiResponse[ZaloStatusResponse])
async def get_status(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ZaloStatusResponse]:
    return ApiResponse.ok(await ZaloService(db=db).status(user_id))


@router.delete("/connection", response_model=ApiResponse[ZaloStatusResponse])
async def disconnect(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ZaloStatusResponse]:
    service = ZaloService(db=db)
    await service.disconnect(user_id)
    return ApiResponse.ok(await service.status(user_id))


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, db: DBSession) -> dict[str, bool]:
    """Nhận sự kiện OA (khách follow/nhắn) → gắn zalo_user_id cho khách.

    Ở chế độ `real` bắt buộc verify chữ ký `X-ZEvent-Signature`. Ở `mock` bỏ qua verify (không
    có secret thật). Luôn trả 200 để Zalo không retry — nghiệp vụ xử lý im lặng bên trong.
    """
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return {"ok": True}
    if not isinstance(payload, dict):
        return {"ok": True}

    if settings.zalo_mode == "real":
        mac = request.headers.get("X-ZEvent-Signature", "").removeprefix("mac=")
        ok = verify_zalo_signature(
            app_id=settings.zalo_app_id,
            oa_secret=settings.zalo_app_secret,
            raw_body=raw,
            timestamp=str(payload.get("timestamp", "")),
            provided_mac=mac,
        )
        if not ok:
            log.warning("zalo.webhook_bad_signature")
            return {"ok": False}

    await ZaloService(db=db).process_webhook_event(payload)
    return {"ok": True}
