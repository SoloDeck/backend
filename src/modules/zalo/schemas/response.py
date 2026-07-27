"""Schema trả về cho các endpoint Zalo OA."""

from pydantic import BaseModel


class ZaloConnectUrlResponse(BaseModel):
    """URL để FE mở cho freelancer cấp quyền OA (ở mock: trỏ thẳng về callback)."""

    url: str


class ZaloStatusResponse(BaseModel):
    """Trạng thái kết nối OA của freelancer — KHÔNG bao giờ lộ access/refresh token."""

    connected: bool
    oa_id: str | None = None
    mode: str  # "mock" | "real"
