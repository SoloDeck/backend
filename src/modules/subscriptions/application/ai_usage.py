"""Cổng kiểm soát mọi lượt gọi AI: có quyền không, còn lượt không, và ghi lại.

Trước đây KHÔNG có cổng nào:

1. ``POST /ai/leads/qualify`` **không đòi token** — bất kỳ ai trên internet cũng gọi
   được, mỗi lần gọi là đốt quota Groq của chủ hệ thống.
2. ``DealsService._run_ai_qualification`` truyền thẳng ``user_can_use_ai=True`` kèm
   comment ``# TODO: get from subscriptions`` — user gói ``free`` dùng AI miễn phí.
3. Bảng ``usage_records`` **rỗng 0 dòng**: không ai ghi lượt dùng. Gói Pro giới hạn
   50 lượt/tháng nhưng **không ai chặn** — gọi bao nhiêu cũng được. Endpoint
   ``GET /analytics/ai-usage`` cộng từ bảng đó nên **luôn trả về 0**, tức là nói dối.

Giờ mọi đường vào AI đều đi qua ``AiUsageService.consume()``.  #Huynh
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    AiCostRecordModel,
    PlanModel,
    SubscriptionModel,
    UsageRecordModel,
)
from src.shared.exceptions.domain import EntitlementError, RateLimitError

log = structlog.get_logger(__name__)

# Khớp ĐÚNG enum trong Postgres — sai một chữ là Postgres từ chối và transaction vỡ.
_AI_STATUSES = frozenset({"pending", "completed", "failed"})
_AI_MODULES = frozenset(
    {"lead_qualifier", "proposal_generator", "contract_generator", "followup_generator"}
)


@dataclass
class AiUsageService:
    db: AsyncSession

    async def consume(self, user_id: uuid.UUID) -> None:
        """Kiểm tra quyền + hạn mức, rồi GHI NHẬN một lượt dùng AI.

        Gọi TRƯỚC khi chạy AI. Ném lỗi thì không được chạy:

        - Không có gói / gói không có AI  -> ``EntitlementError``  (HTTP 402)
        - Hết hạn mức tháng               -> ``RateLimitError``    (HTTP 429)

        Cố ý đếm TRƯỚC khi gọi model, không phải sau: gọi Groq là đã tốn tiền thật rồi,
        dù kết quả có parse được hay không. Đếm sau là mời người ta lách.
        """
        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is None:
            raise EntitlementError(
                "Your plan does not include AI features. Upgrade to Pro.",
                entitlement="can_use_ai",
            )

        plan = await self.db.scalar(select(PlanModel).where(PlanModel.id == sub.plan_id))
        if plan is None or not plan.can_use_ai:
            raise EntitlementError(
                "Your plan does not include AI features. Upgrade to Pro.",
                entitlement="can_use_ai",
            )

        record = await self._get_or_create_record(user_id, sub)
        limit = plan.max_ai_generations_per_month

        # limit <= 0 nghĩa là gói không cho dùng AI (gói free để 0). Đã chặn ở can_use_ai
        # bên trên, nhưng giữ lại phòng khi dữ liệu gói bị cấu hình lệch.
        if limit > 0 and record.ai_generations_used >= limit:
            raise RateLimitError(
                f"Đã dùng hết {limit} lượt AI trong kỳ này. "
                f"Hạn mức làm mới vào {record.billing_period_end:%d/%m/%Y}."
            )

        record.ai_generations_used += 1
        await self.db.flush()

    async def _get_or_create_record(
        self, user_id: uuid.UUID, sub: SubscriptionModel
    ) -> UsageRecordModel:
        """Bản ghi dùng của KỲ THANH TOÁN hiện tại.

        Bám theo `current_period_start` của gói, không phải mốc đầu tháng dương lịch —
        người đăng ký ngày 20 thì kỳ của họ chạy từ 20 tới 20, chứ không reset vào ngày 1.
        """
        record = await self.db.scalar(
            select(UsageRecordModel).where(
                UsageRecordModel.user_id == user_id,
                UsageRecordModel.billing_period_start == sub.current_period_start,
            )
        )
        if record is not None:
            return record

        record = UsageRecordModel(
            id=uuid.uuid4(),
            user_id=user_id,
            subscription_id=sub.id,
            billing_period_start=sub.current_period_start,
            billing_period_end=sub.current_period_end,
            ai_generations_used=0,
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def record_cost(
        self,
        user_id: uuid.UUID,
        *,
        ai_module: str,
        usage: dict[str, Any] | None,
        status: str = "completed",
    ) -> None:
        """Ghi một dòng vào ``ai_cost_records``: module nào, model nào, tốn bao nhiêu token.

        Bảng này có sẵn từ lâu, endpoint ``GET /admin/ai-costs`` cũng có sẵn — nhưng
        KHÔNG AI GHI VÀO. Bảng 0 dòng nên màn hình admin luôn rỗng. Đúng bệnh của
        ``usage_records``: hạ tầng đủ, thiếu đúng người gọi.

        Groq trả token thật trong ``response.usage``, ta vốn vứt đi. Giờ giữ lại.

        ``status`` PHẢI thuộc enum ``ai_generation_status`` = pending | completed | failed.
        Tôi từng để mặc định ``"success"`` — không có trong enum, Postgres từ chối, và
        **cái try/except "để không làm hỏng request" lại phản tác dụng**: flush lỗi làm
        hỏng cả transaction (PendingRollbackError), nên request chết luôn với HTTP 500.
        Nuốt lỗi không hoàn tác được một transaction đã vỡ. Giờ validate TRƯỚC khi ghi.
          #Huynh
        """
        if not usage:
            return

        if status not in _AI_STATUSES:
            log.warning("ai_usage.invalid_status", status=status, module=ai_module)
            status = "completed"

        if ai_module not in _AI_MODULES:
            log.warning("ai_usage.invalid_module", module=ai_module)
            return

        self.db.add(
            AiCostRecordModel(
                id=uuid.uuid4(),
                user_id=user_id,
                ai_module=ai_module,
                model_used=usage.get("model_used", ""),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                estimated_cost_usd=usage.get("estimated_cost_usd", 0),
                status=status,
                occurred_at=datetime.now(UTC),
            )
        )
        await self.db.flush()

    async def summary(self, user_id: uuid.UUID) -> dict:
        """Đã dùng bao nhiêu / còn bao nhiêu trong kỳ này."""
        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is None:
            return {"used": 0, "limit": 0, "remaining": 0, "can_use_ai": False}

        plan = await self.db.scalar(select(PlanModel).where(PlanModel.id == sub.plan_id))
        record = await self.db.scalar(
            select(UsageRecordModel).where(
                UsageRecordModel.user_id == user_id,
                UsageRecordModel.billing_period_start == sub.current_period_start,
            )
        )

        used = record.ai_generations_used if record else 0
        limit = plan.max_ai_generations_per_month if plan else 0

        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "can_use_ai": bool(plan and plan.can_use_ai),
            "period_start": sub.current_period_start,
            "period_end": sub.current_period_end,
        }
