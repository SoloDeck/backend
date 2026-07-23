"""Cấu hình quy tắc nhắc tự động của freelancer."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ReminderRuleModel, UserModel
from src.modules.reminders.domain.value_objects.reminder_rules import (
    REPEATABLE_RULES,
    RULE_DEFAULTS,
    RuleType,
)
from src.shared.exceptions.domain import NotFoundError, ValidationError


@dataclass
class ReminderRulesService:
    db: AsyncSession

    async def list_for_user(self, user_id: uuid.UUID) -> list[ReminderRuleModel]:
        """Trả về đủ 5 quy tắc, tự tạo bộ mặc định nếu user chưa có.

        Sinh LƯỜI ở đây chứ không backfill trong migration: user đăng ký ngày mai vẫn có
        đủ quy tắc mà không ai phải nhớ chạy lại script. Đây cũng là lý do hàm này chịu
        trách nhiệm tạo chứ không phải luồng đăng ký — thêm việc vào đăng ký là thêm một
        chỗ nữa có thể quên.  #Huynh
        """
        existing = await self._fetch(user_id)
        missing = [rule for rule in RuleType if rule not in {r.rule_type for r in existing}]
        if not missing:
            return self._sorted(existing)

        # Kênh mặc định lấy theo tuỳ chọn sẵn có của người dùng thay vì áp cứng — họ đã
        # khai một lần ở phần Tuỳ chọn rồi, hỏi lại là thừa.
        channel = await self._default_channel(user_id)
        for rule_type in missing:
            spec = RULE_DEFAULTS[rule_type]
            self.db.add(
                ReminderRuleModel(
                    owner_user_id=user_id,
                    rule_type=rule_type.value,
                    is_enabled=spec.is_enabled,
                    offset_days=spec.offset_days,
                    repeat_every_days=spec.repeat_every_days,
                    channel=channel,
                    auto_send=False,
                    send_at_hour=9,
                )
            )
        await self.db.flush()
        return self._sorted(await self._fetch(user_id))

    async def update(
        self,
        user_id: uuid.UUID,
        rule_type: str,
        *,
        is_enabled: bool | None = None,
        offset_days: int | None = None,
        repeat_every_days: int | None = None,
        channel: str | None = None,
        auto_send: bool | None = None,
        send_at_hour: int | None = None,
    ) -> ReminderRuleModel:
        if rule_type not in {r.value for r in RuleType}:
            raise ValidationError(
                f"rule_type phải là một trong {sorted(r.value for r in RuleType)}"
            )

        # Gọi list_for_user trước để user chưa có quy tắc nào vẫn sửa được ngay, thay vì
        # bắt họ GET một lần cho có rồi mới PATCH được.
        await self.list_for_user(user_id)
        rule = await self.db.scalar(
            select(ReminderRuleModel).where(
                ReminderRuleModel.owner_user_id == user_id,
                ReminderRuleModel.rule_type == rule_type,
            )
        )
        if rule is None:
            raise NotFoundError(f"Reminder rule {rule_type} not found")

        if offset_days is not None:
            if not 0 <= offset_days <= 365:
                raise ValidationError("offset_days phải từ 0 đến 365 ngày.")
            rule.offset_days = offset_days

        if repeat_every_days is not None:
            if RuleType(rule_type) not in REPEATABLE_RULES:
                # Nhắc mãi một báo giá khách đã lờ đi thì không phải chăm sóc mà là làm
                # phiền — chặn ở đây thay vì để dữ liệu vô nghĩa lọt vào bảng.
                raise ValidationError(
                    f"Quy tắc '{rule_type}' không hỗ trợ lặp lại, chỉ nhắc một lần."
                )
            if not 1 <= repeat_every_days <= 365:
                raise ValidationError("repeat_every_days phải từ 1 đến 365 ngày.")
            rule.repeat_every_days = repeat_every_days

        if send_at_hour is not None:
            if not 0 <= send_at_hour <= 23:
                raise ValidationError("send_at_hour phải từ 0 đến 23.")
            rule.send_at_hour = send_at_hour

        if channel is not None:
            if channel not in {"email", "in_app", "both", "zalo"}:
                raise ValidationError(f"channel không hợp lệ: {channel!r}")
            rule.channel = channel

        if is_enabled is not None:
            rule.is_enabled = is_enabled
        if auto_send is not None:
            rule.auto_send = auto_send

        await self.db.flush()
        await self.db.refresh(rule)
        return rule

    # --- Phụ trợ -------------------------------------------------------------------

    async def _fetch(self, user_id: uuid.UUID) -> list[ReminderRuleModel]:
        result = await self.db.execute(
            select(ReminderRuleModel).where(ReminderRuleModel.owner_user_id == user_id)
        )
        return list(result.scalars().all())

    async def _default_channel(self, user_id: uuid.UUID) -> str:
        user = await self.db.scalar(select(UserModel).where(UserModel.id == user_id))
        return user.notification_channel if user else "in_app"

    @staticmethod
    def _sorted(rules: list[ReminderRuleModel]) -> list[ReminderRuleModel]:
        """Giữ thứ tự theo vòng đời deal, không phải theo thứ tự chèn vào bảng — màn cài
        đặt đọc xuôi từ báo giá tới thanh toán mới dễ hiểu."""
        order = {rule.value: index for index, rule in enumerate(RuleType)}
        return sorted(rules, key=lambda r: order.get(r.rule_type, 99))
