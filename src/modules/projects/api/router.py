"""Projects and tasks endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.projects.application.service import ProjectsService
from src.modules.projects.schemas.request import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from src.modules.projects.schemas.response import (
    ProjectResponse,
    TaskListResponse,
    TaskResponse,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


# ------------------------------------------------------------------
# Projects
# ------------------------------------------------------------------

@router.post("", response_model=ApiResponse[ProjectResponse], status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectsService(db=db).create_project(user_id, payload)
    return ApiResponse.created(ProjectResponse.model_validate(project))


@router.get("", response_model=ApiResponse[list[ProjectResponse]])
async def list_projects(
    user_id: CurrentUserId,
    db: DBSession,
    deal_id: uuid.UUID | None = Query(default=None, description="Filter by deal"),
) -> ApiResponse[list[ProjectResponse]]:
    projects = await ProjectsService(db=db).list_projects(user_id, deal_id=deal_id)
    return ApiResponse.ok([ProjectResponse.model_validate(p) for p in projects])


@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def get_project(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectsService(db=db).get_project(user_id, project_id)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectsService(db=db).update_project(user_id, project_id, payload)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.delete("/{project_id}", response_model=ApiResponse[MsgResp])
async def delete_project(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ProjectsService(db=db).delete_project(user_id, project_id)
    return ApiResponse.ok(MsgResp(detail="Project deleted"))


# ------------------------------------------------------------------
# Tasks (nested under project)
# ------------------------------------------------------------------

@router.get("/{project_id}/tasks", response_model=ApiResponse[TaskListResponse])
async def list_tasks(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskListResponse]:
    tasks, total, done, percent = await ProjectsService(db=db).list_tasks(user_id, project_id)
    return ApiResponse.ok(
        TaskListResponse(
            tasks=[TaskResponse.model_validate(t) for t in tasks],
            total=total,
            done=done,
            percent=percent,
        )
    )


@router.post("/{project_id}/tasks", response_model=ApiResponse[TaskResponse], status_code=201)
async def create_task(
    project_id: uuid.UUID,
    payload: TaskCreateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    task = await ProjectsService(db=db).create_task(user_id, project_id, payload)
    return ApiResponse.created(TaskResponse.model_validate(task))


@router.patch("/{project_id}/tasks/{task_id}", response_model=ApiResponse[TaskResponse])
async def update_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskUpdateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TaskResponse]:
    task = await ProjectsService(db=db).update_task(user_id, project_id, task_id, payload)
    return ApiResponse.ok(TaskResponse.model_validate(task))


@router.delete("/{project_id}/tasks/{task_id}", response_model=ApiResponse[MsgResp])
async def delete_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ProjectsService(db=db).delete_task(user_id, project_id, task_id)
    return ApiResponse.ok(MsgResp(detail="Task deleted"))
