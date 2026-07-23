"""Reminders API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.reminders.application.service import RemindersService
from src.modules.reminders.schemas.request import ReminderRequest
from src.modules.reminders.schemas.response import ReminderDeliveryResponse, ReminderResponse
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
