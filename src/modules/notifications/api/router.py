"""API thông báo trong ứng dụng (cái chuông trên thanh tiêu đề)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.notifications.application.service import NotificationService
from src.modules.notifications.schemas.response import (
    NotificationResponse,
    UnreadCountResponse,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.exceptions.domain import NotFoundError
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MarkReadResponse(BaseModel):
    marked: int


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    user_id: CurrentUserId,
    db: DBSession,
    unread_only: bool = Query(default=False, description="Chỉ lấy thông báo chưa đọc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[NotificationResponse]:
    rows, total = await NotificationService(db=db).list_for_user(
        user_id, unread_only=unread_only, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [NotificationResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=ApiResponse[UnreadCountResponse])
async def count_unread(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UnreadCountResponse]:
    """Endpoint riêng cho cái chấm đỏ: gọi thường xuyên nên phải rẻ."""
    count = await NotificationService(db=db).count_unread(user_id)
    return ApiResponse.ok(UnreadCountResponse(unread_count=count))


@router.patch("/{notification_id}/read", response_model=ApiResponse[MarkReadResponse])
async def mark_read(
    notification_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MarkReadResponse]:
    ok = await NotificationService(db=db).mark_read(user_id, notification_id)
    if not ok:
        # Không phân biệt "không tồn tại" với "không phải của bạn": nói ra là để lộ việc id
        # đó có tồn tại trong hệ thống hay không.  #Huynh
        raise NotFoundError("Thông báo không tồn tại")
    return ApiResponse.ok(MarkReadResponse(marked=1))


@router.post("/read-all", response_model=ApiResponse[MarkReadResponse])
async def mark_all_read(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MarkReadResponse]:
    marked = await NotificationService(db=db).mark_all_read(user_id)
    return ApiResponse.ok(MarkReadResponse(marked=marked))
