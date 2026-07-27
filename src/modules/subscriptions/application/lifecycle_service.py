"""Cảnh báo EMAIL quanh vòng đời gói trả phí: báo trước khi sắp hết kỳ.

Chạy MỖI NGÀY qua Celery beat (`run_subscription_maintenance`). Thuần async, để test bằng
AsyncMock và chạy tay lúc kiểm chứng, cùng lối `AutoReminderScheduler`.

CHỈ CẢNH BÁO — KHÔNG hạ gói. Việc tự hạ về Free khi hết kỳ do
`SubscriptionsService.expire_lapsed_subscriptions()` (module subscriptions, gắn với luồng
thanh toán MoMo) lo. Tách bạch để tránh hai nơi cùng hạ gói.

Cố ý KHÔNG cần cột cờ mới: cảnh báo sắp hết kỳ chỉ bắn ĐÚNG ngày còn `EXPIRY_WARN_DAYS`
ngày (job chạy 1 lần/ngày nên chỉ đúng một lần lọt qua mốc này). Cảnh báo sắp-hết-quota
xử lý ngay trong `AiUsageService.consume`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.infrastructure.database.models import PlanModel, SubscriptionModel, UserModel
from src.modules.subscriptions.application.emails import (
    EmailContent,
    build_expiry_warning_email,
)
from src.shared.email.smtp import send_email

log = structlog.get_logger(__name__)

# Số ngày trước hạn để gửi email báo trước. Chỉnh được khi chốt nghiệp vụ.
EXPIRY_WARN_DAYS = 3
# Gói free tra theo slug (khớp auth/seeders) — dùng để LỌC ra gói trả phí (slug != free).
FREE_PLAN_SLUG = "free"


@dataclass
class SubscriptionLifecycleService:
    db: AsyncSession
    now: datetime | None = None  # test hook: cố định "bây giờ"

    def _now(self) -> datetime:
        return self.now or datetime.now(UTC)

    async def run_daily_maintenance(self) -> dict[str, int]:
        warned = await self._warn_expiring_soon()
        return {"expiry_warned": warned}

    # --- Cảnh báo sắp hết kỳ -------------------------------------------------------

    async def _warn_expiring_soon(self) -> int:
        now = self._now()
        sent = 0
        for sub, plan, user in await self._paid_active_subs():
            # `.days` cắt phần lẻ; job chạy 1 lần/ngày nên chỉ đúng một ngày bằng mốc này.
            days_left = (sub.current_period_end - now).days
            if days_left != EXPIRY_WARN_DAYS or not user.email:
                continue
            content = build_expiry_warning_email(
                owner_name=user.full_name,
                plan_name=plan.name,
                period_end=sub.current_period_end,
                days_left=days_left,
                plan_url=self._plan_url(),
            )
            if await self._safe_send(user.email, content, user.id):
                sent += 1
        return sent

    # --- Phụ trợ -------------------------------------------------------------------

    async def _paid_active_subs(self) -> list[Any]:
        """Sub đang `active` của gói TRẢ PHÍ (slug != free), kèm plan + user."""
        rows = await self.db.execute(
            select(SubscriptionModel, PlanModel, UserModel)
            .join(PlanModel, PlanModel.id == SubscriptionModel.plan_id)
            .join(UserModel, UserModel.id == SubscriptionModel.user_id)
            .where(
                SubscriptionModel.status == "active",
                PlanModel.slug != FREE_PLAN_SLUG,
                UserModel.deleted_at.is_(None),
            )
        )
        return list(rows.all())

    @staticmethod
    def _plan_url() -> str:
        return f"{settings.frontend_url.rstrip('/')}/?tab=subscription"

    async def _safe_send(self, to: str, content: EmailContent, user_id: uuid.UUID) -> bool:
        # Best-effort: một email hỏng không được làm hỏng lượt bảo trì của các user khác.
        try:
            await send_email(
                to=to, subject=content.subject, html=content.html, plain=content.plain
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("subscription_email.failed", user_id=str(user_id), error=str(exc))
            return False
