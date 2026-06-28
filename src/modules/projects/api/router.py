"""Projects API router.

Mounted at /api/v1/projects. Task sub-resources (/projects/{id}/tasks) live in
the tasks module router, which is mounted separately.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.modules.projects.application.service import ProjectService
from src.modules.projects.domain.value_objects.project_status import ProjectStatus
from src.modules.projects.schemas.request import CreateProjectRequest, UpdateProjectRequest
from src.modules.projects.schemas.response import ProjectResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.db import DBSession
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()


@router.post("", response_model=ApiResponse[ProjectResponse], status_code=201)
async def create_project(
    payload: CreateProjectRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectService(db=db).create(user_id, payload)
    return ApiResponse.created(ProjectResponse.model_validate(project))


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    user_id: CurrentUserId,
    db: DBSession,
    deal_id: Annotated[uuid.UUID | None, Query(description="Filter by the linked deal")] = None,
    project_status: Annotated[
        ProjectStatus | None, Query(alias="status", description="Filter by project status")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ProjectResponse]:
    items, total = await ProjectService(db=db).list(
        user_id,
        deal_id=deal_id,
        status=project_status.value if project_status else None,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.ok(
        [ProjectResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def get_project(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectService(db=db).get(project_id, user_id)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.put("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(
    project_id: uuid.UUID,
    payload: UpdateProjectRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProjectResponse]:
    project = await ProjectService(db=db).update(project_id, user_id, payload)
    return ApiResponse.ok(ProjectResponse.model_validate(project))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> None:
    await ProjectService(db=db).delete(project_id, user_id)
