"""Deal tasks (todo list) endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.deals.application.task_service import DealTasksService
from src.modules.deals.schemas.task import (
    DealTaskCreateRequest,
    DealTaskListResponse,
    DealTaskResponse,
    DealTaskUpdateRequest,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.get("/{deal_id}/tasks", response_model=ApiResponse[DealTaskListResponse])
async def list_tasks(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealTaskListResponse]:
    tasks, total, done, percent = await DealTasksService(db=db).list_tasks(user_id, deal_id)
    return ApiResponse.ok(
        DealTaskListResponse(
            tasks=[DealTaskResponse.model_validate(t) for t in tasks],
            total=total,
            done=done,
            percent=percent,
        )
    )


@router.post("/{deal_id}/tasks", response_model=ApiResponse[DealTaskResponse], status_code=201)
async def create_task(
    deal_id: uuid.UUID,
    payload: DealTaskCreateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealTaskResponse]:
    task = await DealTasksService(db=db).create_task(user_id, deal_id, payload)
    return ApiResponse.created(DealTaskResponse.model_validate(task))


@router.patch("/{deal_id}/tasks/{task_id}", response_model=ApiResponse[DealTaskResponse])
async def update_task(
    deal_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: DealTaskUpdateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealTaskResponse]:
    task = await DealTasksService(db=db).update_task(user_id, deal_id, task_id, payload)
    return ApiResponse.ok(DealTaskResponse.model_validate(task))


@router.delete("/{deal_id}/tasks/{task_id}", response_model=ApiResponse[MsgResp])
async def delete_task(
    deal_id: uuid.UUID,
    task_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await DealTasksService(db=db).delete_task(user_id, deal_id, task_id)
    return ApiResponse.ok(MsgResp(detail="Task deleted"))
