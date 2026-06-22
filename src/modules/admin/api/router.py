"""Admin API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.admin.application.service import AdminService
from src.modules.admin.schemas.request import AdminPlanRequest, AdminUpdateUserRequest
from src.modules.admin.schemas.response import AdminPlanResponse, AdminUserResponse
from src.shared.dependencies.auth import AdminUser
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/users", response_model=ApiResponse[list[AdminUserResponse]])
async def list_users(
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[list[AdminUserResponse]]:
    users = await AdminService(db=db).list_users()
    return ApiResponse.ok([AdminUserResponse.model_validate(u) for u in users])


@router.get("/users/{user_id}", response_model=ApiResponse[AdminUserResponse])
async def get_user(
    user_id: uuid.UUID,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminUserResponse]:
    user = await AdminService(db=db).get_user(user_id)
    return ApiResponse.ok(AdminUserResponse.model_validate(user))


@router.patch("/users/{user_id}", response_model=ApiResponse[AdminUserResponse])
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminUserResponse]:
    user = await AdminService(db=db).update_user(user_id, payload)
    return ApiResponse.ok(AdminUserResponse.model_validate(user))


@router.get("/plans", response_model=ApiResponse[list[AdminPlanResponse]])
async def list_plans(
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[list[AdminPlanResponse]]:
    plans = await AdminService(db=db).list_plans()
    return ApiResponse.ok([AdminPlanResponse.model_validate(p) for p in plans])


@router.post("/plans", response_model=ApiResponse[AdminPlanResponse], status_code=201)
async def create_plan(
    payload: AdminPlanRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlanResponse]:
    plan = await AdminService(db=db).create_plan(payload)
    return ApiResponse.created(AdminPlanResponse.model_validate(plan))


@router.patch("/plans/{plan_id}", response_model=ApiResponse[AdminPlanResponse])
async def update_plan(
    plan_id: uuid.UUID,
    payload: AdminPlanRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlanResponse]:
    plan = await AdminService(db=db).update_plan(plan_id, payload)
    return ApiResponse.ok(AdminPlanResponse.model_validate(plan))
