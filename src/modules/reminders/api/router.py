"""Reminders API api."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.reminders.application.rule_service import ReminderRulesService
from src.modules.reminders.application.service import RemindersService
from src.modules.reminders.domain.value_objects.reminder_rules import (
    REPEATABLE_RULES,
    RULE_DEFAULTS,
    VARIABLE_LABELS,
    RuleType,
    effective_template,
)
from src.modules.reminders.schemas.request import ReminderRequest, ReminderRuleUpdate
from src.modules.reminders.schemas.response import (
    ReminderDeliveryResponse,
    ReminderResponse,
    ReminderRuleResponse,
    ReminderTemplateVariable,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[ReminderResponse], status_code=201)
async def create_reminder(
    payload: ReminderRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).create(user_id, payload)
    return ApiResponse.created(ReminderResponse.model_validate(reminder))


@router.get("", response_model=ApiResponse[list[ReminderResponse]])
async def list_reminders(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(
        default=None, description="Filter by status: pending, sent, failed, cancelled"
    ),
    target_type: str | None = Query(
        default=None, description="Filter by target type: deal, proposal, contract, invoice"
    ),
) -> ApiResponse[list[ReminderResponse]]:
    reminders = await RemindersService(db=db).list_all(
        user_id, status=status, target_type=target_type
    )
    return ApiResponse.ok([ReminderResponse.model_validate(r) for r in reminders])


# ĐẶT TRƯỚC `/{reminder_id}` — FastAPI khớp route theo thứ tự khai báo, để sau thì
# "/reminders/rules" bị nuốt vào route động và trả 422 vì "rules" không phải UUID.  #Huynh
@router.get("/rules", response_model=ApiResponse[list[ReminderRuleResponse]])
async def list_reminder_rules(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[ReminderRuleResponse]]:
    """Năm quy tắc nhắc tự động. Lần gọi đầu tiên tự tạo bộ mặc định."""
    rules = await ReminderRulesService(db=db).list_for_user(user_id)
    return ApiResponse.ok([_rule_response(rule) for rule in rules])


@router.patch("/rules/{rule_type}", response_model=ApiResponse[ReminderRuleResponse])
async def update_reminder_rule(
    rule_type: str,
    payload: ReminderRuleUpdate,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderRuleResponse]:
    rule = await ReminderRulesService(db=db).update(
        user_id, rule_type, **payload.model_dump(exclude_unset=True)
    )
    return ApiResponse.ok(_rule_response(rule))


def _rule_response(rule: Any) -> ReminderRuleResponse:
    rule_type = RuleType(rule.rule_type)
    spec = RULE_DEFAULTS.get(rule_type)
    return ReminderRuleResponse(
        rule_type=rule.rule_type,
        is_enabled=rule.is_enabled,
        offset_days=rule.offset_days,
        repeat_every_days=rule.repeat_every_days,
        channel=rule.channel,
        auto_send=rule.auto_send,
        send_at_hour=rule.send_at_hour,
        label=spec.label if spec else "",
        supports_repeat=rule_type in REPEATABLE_RULES,
        message_template=effective_template(rule_type, rule.message_template),
        is_custom_template=bool((rule.message_template or "").strip()),
        template_variables=[
            ReminderTemplateVariable(token="{" + name + "}", label=VARIABLE_LABELS[name])
            for name in (spec.variables if spec else ())
        ],
    )


@router.get("/{reminder_id}", response_model=ApiResponse[ReminderResponse])
async def get_reminder(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).get_one(user_id, reminder_id)
    return ApiResponse.ok(ReminderResponse.model_validate(reminder))


@router.patch("/{reminder_id}", response_model=ApiResponse[ReminderResponse])
async def update_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).update(user_id, reminder_id, payload)
    return ApiResponse.ok(ReminderResponse.model_validate(reminder))


@router.post("/{reminder_id}/send", response_model=ApiResponse[ReminderDeliveryResponse])
async def send_reminder_now(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderDeliveryResponse]:
    """Gửi lời nhắc ngay, không đợi tới giờ đã hẹn."""
    reminder, result = await RemindersService(db=db).send_now(user_id, reminder_id)
    return ApiResponse.ok(
        ReminderDeliveryResponse(
            reminder=ReminderResponse.model_validate(reminder),
            status=result.status,
            detail=result.detail,
            delivered=result.delivered,
        )
    )


@router.delete("/{reminder_id}", response_model=ApiResponse[MsgResp])
async def cancel_reminder(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await RemindersService(db=db).cancel(user_id, reminder_id)
    return ApiResponse.ok(MsgResp(detail="Reminder cancelled"))
