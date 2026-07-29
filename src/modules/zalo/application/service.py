"""Nghiệp vụ Zalo OA: kết nối OAuth (PKCE), webhook nhận follower, ngắt kết nối.

Callback OAuth bị TRÌNH DUYỆT gọi (Zalo chuyển hướng về) nên KHÔNG mang bearer token —
không biết được ai đang kết nối. Vì thế `state` là một JWT tự ký mang sẵn ``user_id`` +
``code_verifier`` (PKCE), hết hạn 15 phút. Callback đọc state ra để biết freelancer nào và
để hoàn tất PKCE — không cần bảng lưu state.  #Huynh
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.integrations.zalo.client import (
    ZaloOAClient,
    code_challenge_for,
    generate_code_verifier,
    get_zalo_client,
    unusable_redirect_reason,
)
from src.modules.zalo.infrastructure.repository import ZaloRepository
from src.modules.zalo.schemas.response import ZaloStatusResponse
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError, ValidationError

log = structlog.get_logger(__name__)

_STATE_PURPOSE = "zalo_oauth"
_STATE_TTL = timedelta(minutes=15)


def _sign_state(user_id: uuid.UUID, verifier: str) -> str:
    return jwt.encode(
        {
            "uid": str(user_id),
            "cv": verifier,
            "purpose": _STATE_PURPOSE,
            "exp": datetime.now(UTC) + _STATE_TTL,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _read_state(state: str) -> tuple[uuid.UUID, str]:
    payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != _STATE_PURPOSE:
        raise ValidationError("Trạng thái kết nối Zalo không hợp lệ.")
    return uuid.UUID(payload["uid"]), payload["cv"]


@dataclass
class ZaloService:
    db: AsyncSession
    repo: ZaloRepository | None = None
    # Tiêm client để test bơm mock, và để đổi real/mock bằng config mà không sửa nghiệp vụ.
    client: ZaloOAClient | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ZaloRepository(self.db)
        if self.client is None:
            self.client = get_zalo_client(settings)

    async def build_connect_url(self, user_id: uuid.UUID) -> str:
        """URL để freelancer cấp quyền OA. Sinh verifier PKCE, ký vào state."""
        # Chặn TRƯỚC khi đẩy người dùng sang Zalo.
        #
        # Thiếu config ở chế độ `real` thì `RealZaloOAClient` vẫn dựng URL bình thường,
        # chỉ là thiếu `redirect_uri`/`app_id` — người dùng bấm "Kết nối", nhảy sang Zalo,
        # rồi ăn một trang lỗi `-14003` bằng tiếng Anh không nói gì về nguyên nhân. Báo
        # ngay tại đây thì họ biết là cấu hình phía mình, không phải Zalo dở.
        #
        # CHỈ chặn ở đây, KHÔNG chặn trong `__post_init__` hay `get_zalo_client`: hai chỗ
        # đó chạy cho cả `/status` và `/connection`, chặn ở đó là làm hỏng luôn màn Cài
        # đặt của mọi người chỉ vì phần OAuth chưa khai xong.  #Huynh
        if settings.zalo_mode == "real":
            if not settings.zalo_app_id:
                raise BusinessRuleError(
                    "Kết nối Zalo OA chưa được cấu hình trên máy chủ (thiếu ZALO_APP_ID). "
                    "Báo quản trị viên giúp nhé."
                )
            # Không chỉ kiểm RỖNG mà kiểm DÙNG ĐƯỢC KHÔNG. Một URL ngrok còn sót trong
            # `.env` là "có giá trị" nhưng Zalo vẫn từ chối — lần trước rơi đúng vào đó và
            # chỉ nhận được trang `error_code=-14003` không nói gì thêm.  #Huynh
            reason = unusable_redirect_reason(settings.zalo_oauth_redirect_uri)
            if reason:
                raise BusinessRuleError(
                    f"Kết nối Zalo OA chưa dùng được: ZALO_OAUTH_REDIRECT_URI {reason}. "
                    "Báo quản trị viên giúp nhé."
                )

        verifier = generate_code_verifier()
        challenge = code_challenge_for(verifier)
        state = _sign_state(user_id, verifier)
        assert self.client is not None
        return self.client.build_oauth_url(state=state, code_challenge=challenge)

    async def complete_connection(self, *, code: str, state: str) -> None:
        """Callback: đổi code lấy token, lấy oa_id, lưu lên user. Ném lỗi thì router điều
        hướng về FE kèm cờ báo lỗi."""
        try:
            user_id, verifier = _read_state(state)
        except JWTError as exc:
            raise ValidationError("Liên kết kết nối Zalo đã hết hạn hoặc không hợp lệ.") from exc

        assert self.repo is not None and self.client is not None
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Không tìm thấy người dùng để gắn Zalo OA.")

        token = await self.client.exchange_code(code=code, code_verifier=verifier)
        oa_id = await self.client.get_oa_id(access_token=token.access_token)

        user.zalo_oa_app_id = oa_id
        user.zalo_oa_access_token = token.access_token
        user.zalo_oa_refresh_token = token.refresh_token
        await self.repo.save(user)
        log.info("zalo.connected", user_id=str(user_id), oa_id=oa_id, mode=settings.zalo_mode)

    async def status(self, user_id: uuid.UUID) -> ZaloStatusResponse:
        assert self.repo is not None
        user = await self.repo.get_user(user_id)
        connected = bool(user and user.zalo_oa_access_token)
        return ZaloStatusResponse(
            connected=connected,
            oa_id=user.zalo_oa_app_id if (connected and user) else None,
            mode=settings.zalo_mode,
        )

    async def disconnect(self, user_id: uuid.UUID) -> None:
        assert self.repo is not None
        user = await self.repo.get_user(user_id)
        if user is None:
            return
        user.zalo_oa_app_id = None
        user.zalo_oa_access_token = None
        user.zalo_oa_refresh_token = None
        await self.repo.save(user)
        log.info("zalo.disconnected", user_id=str(user_id))

    async def process_webhook_event(self, payload: dict[str, Any]) -> None:
        """Khách nhắn/follow OA → gắn ``zalo_user_id`` cho đúng khách theo SĐT.

        Cố ý IM LẶNG khi thiếu dữ kiện (không có oa_id / user_id / phone, không khớp OA hay
        khách): webhook của bên thứ ba không nên làm request 4xx/5xx vì một sự kiện ta chưa
        map được — Zalo sẽ retry ầm ĩ. Nhận 200 rồi bỏ qua là đúng.
        """
        oa_id = str(payload.get("oa_id") or "").strip()
        sender = payload.get("sender") or payload.get("follower") or {}
        zalo_user_id = str(sender.get("id") or "").strip()
        phone = _extract_phone(payload)
        if not (oa_id and zalo_user_id and phone):
            return

        assert self.repo is not None
        owner = await self.repo.get_user_by_oa_id(oa_id)
        if owner is None:
            return
        client = await self.repo.get_client_by_phone(owner.id, phone)
        if client is None:
            return

        client.zalo_user_id = zalo_user_id
        await self.repo.save(client)
        log.info(
            "zalo.follower_linked",
            owner_id=str(owner.id),
            client_id=str(client.id),
            zalo_user_id=zalo_user_id,
        )


def _extract_phone(payload: dict[str, Any]) -> str:
    """Rút số điện thoại từ payload webhook (khách chia sẻ SĐT hoặc event kèm info).

    Zalo đặt SĐT ở vài chỗ tuỳ loại sự kiện; thử lần lượt. Không có thì trả "" → bỏ qua.
    """
    for path in (
        ("info", "phone"),
        ("sender", "phone"),
        ("message", "phone"),
        ("phone",),
    ):
        node: object = payload
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                node = None
                break
        if isinstance(node, str) and node.strip():
            return node.strip()
    return ""
