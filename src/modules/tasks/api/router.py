"""Tasks API router (polymorphic).

Mounted with the bare /api/v1 prefix so it can expose task entry points nested
under three different parents plus the flat /tasks resource:

    /projects/{project_id}/tasks      entity_type=project
    /deals/{deal_id}/tasks            entity_type=deal
    /reminders/{reminder_id}/tasks    entity_type=reminder
    /tasks/{task_id}                  direct access
    /tasks/{task_id}/checklist[...]   checklist sub-resource

Every handler funnels into the single shared TaskService.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.modules.tasks.application.service import TaskService
from src.modules.tasks.domain.value_objects.task_status import TaskStatus
from src.modules.tasks.schemas.request import (
    CreateChecklistItemRequest,
    CreateTaskRequest,
    UpdateChecklistItemRequest,
    UpdateTaskRequest,
)
from src.modules.tasks.schemas.response import ChecklistItemResponse, TaskResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.db import DBSession
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

StatusQuery = Annotated[TaskStatus | None, Query(description="Filter by task status")]
PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]


async def _list(
    entity_type: str,
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DBSession,
    task_status: TaskStatus | None,
    page: int,
    page_size: int,
) -> PaginatedResponse[TaskResponse]:
    items, total = await TaskService(db=db).list_by_entity(
        entity_type,
        entity_id,
        user_id,
        status=task_status.value if task_status else None,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.ok(
        [TaskResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _create(
    entity_type: str,
    entity_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DBSession,
    payload: CreateTaskRequest,
) -> ApiResponse[TaskResponse]:
    task = await TaskService(db=db).create_for_entity(entity_type, entity_id, user_id, payload)
    return ApiResponse.created(TaskResponse.model_validate(task))


# --- Project tasks -----------------------------------------------------------
@router.get("/projects/{project_id}/tasks", response_model=PaginatedResponse[TaskResponse])
async def list_project_tasks(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    task_status: StatusQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> PaginatedResponse[TaskResponse]:
    return await _list("project", project_id, user_id, db, task_status, page, page_size)


@router.post(
    "/projects/{project_id}/tasks",
    response_model=ApiResponse[TaskResponse],
    status_code=201,
)
async def create_project_task(
    project_id: uuid.UUID,
    payload: CreateTaskRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    return await _create("project", project_id, user_id, db, payload)


# --- Deal tasks --------------------------------------------------------------
@router.get("/deals/{deal_id}/tasks", response_model=PaginatedResponse[TaskResponse])
async def list_deal_tasks(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    task_status: StatusQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> PaginatedResponse[TaskResponse]:
    return await _list("deal", deal_id, user_id, db, task_status, page, page_size)


@router.post(
    "/deals/{deal_id}/tasks",
    response_model=ApiResponse[TaskResponse],
    status_code=201,
)
async def create_deal_task(
    deal_id: uuid.UUID,
    payload: CreateTaskRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    return await _create("deal", deal_id, user_id, db, payload)


# --- Reminder tasks ----------------------------------------------------------
@router.get("/reminders/{reminder_id}/tasks", response_model=PaginatedResponse[TaskResponse])
async def list_reminder_tasks(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    task_status: StatusQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
) -> PaginatedResponse[TaskResponse]:
    return await _list("reminder", reminder_id, user_id, db, task_status, page, page_size)


@router.post(
    "/reminders/{reminder_id}/tasks",
    response_model=ApiResponse[TaskResponse],
    status_code=201,
)
async def create_reminder_task(
    reminder_id: uuid.UUID,
    payload: CreateTaskRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    return await _create("reminder", reminder_id, user_id, db, payload)


# --- Direct task access ------------------------------------------------------
@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(
    task_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    task = await TaskService(db=db).get(task_id, user_id)
    return ApiResponse.ok(TaskResponse.model_validate(task))


@router.patch("/tasks/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(
    task_id: uuid.UUID,
    payload: UpdateTaskRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    task = await TaskService(db=db).update(task_id, user_id, payload)
    return ApiResponse.ok(TaskResponse.model_validate(task))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> None:
    await TaskService(db=db).delete(task_id, user_id)


# --- Checklist items ---------------------------------------------------------
@router.post(
    "/tasks/{task_id}/checklist",
    response_model=ApiResponse[ChecklistItemResponse],
    status_code=201,
)
async def add_checklist_item(
    task_id: uuid.UUID,
    payload: CreateChecklistItemRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ChecklistItemResponse]:
    item = await TaskService(db=db).add_checklist_item(task_id, user_id, payload)
    return ApiResponse.created(ChecklistItemResponse.model_validate(item))


@router.patch(
    "/tasks/{task_id}/checklist/{item_id}",
    response_model=ApiResponse[ChecklistItemResponse],
)
async def update_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: UpdateChecklistItemRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ChecklistItemResponse]:
    item = await TaskService(db=db).update_checklist_item(task_id, item_id, user_id, payload)
    return ApiResponse.ok(ChecklistItemResponse.model_validate(item))


@router.delete(
    "/tasks/{task_id}/checklist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> None:
    await TaskService(db=db).delete_checklist_item(task_id, item_id, user_id)
