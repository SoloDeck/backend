"""Admin API router."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.admin.application.service import AdminService
from src.modules.admin.schemas.request import (
    AdminCreateTemplateRequest,
    AdminPlanRequest,
    AdminSubscriptionOverrideRequest,
    AdminUpdateFeatureFlagRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
)
from src.modules.admin.schemas.response import (
    AdminAiCostPagedResponse,
    AdminAiCostResponse,
    AdminAiCostTotals,
    AdminAuditLogResponse,
    AdminFeatureFlagResponse,
    AdminPlanResponse,
    AdminPlatformMetricsResponse,
    AdminSubscriptionResponse,
    AdminTemplateResponse,
    AdminUserResponse,
    Paginated,
)
from src.shared.dependencies.auth import AdminUser
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sub_to_response(sub, plan) -> AdminSubscriptionResponse:
    return AdminSubscriptionResponse(
        id=sub.id,
        user_id=sub.user_id,
        plan_id=sub.plan_id,
        plan_name=plan.name,
        plan_slug=plan.slug,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
        cancelled_at=sub.cancelled_at,
        override_expires_at=sub.override_expires_at,
        created_at=sub.created_at,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=ApiResponse[Paginated[AdminUserResponse]])
async def list_users(
    _: AdminUser,
    db: DBSession,
    status: str | None = Query(default=None),
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    plan_slug: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Paginated[AdminUserResponse]]:
    users, total = await AdminService(db=db).list_users_paginated(
        status=status,
        role=role,
        search=search,
        plan_slug=plan_slug,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return ApiResponse.ok(
        Paginated[AdminUserResponse](
            data=[AdminUserResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


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


@router.post("/users/{user_id}/suspend", response_model=ApiResponse[AdminUserResponse])
async def suspend_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminUserResponse]:
    user = await AdminService(db=db).suspend_user(
        user_id, admin_id=uuid.UUID(admin.sub)
    )
    return ApiResponse.ok(AdminUserResponse.model_validate(user))


@router.post("/users/{user_id}/reinstate", response_model=ApiResponse[AdminUserResponse])
async def reinstate_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminUserResponse]:
    user = await AdminService(db=db).reinstate_user(
        user_id, admin_id=uuid.UUID(admin.sub)
    )
    return ApiResponse.ok(AdminUserResponse.model_validate(user))


@router.delete("/users/{user_id}/sessions", status_code=204)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    _: AdminUser,
    db: DBSession,
) -> Response:
    await AdminService(db=db).revoke_user_sessions(user_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@router.get("/subscriptions", response_model=ApiResponse[Paginated[AdminSubscriptionResponse]])
async def list_subscriptions(
    _: AdminUser,
    db: DBSession,
    status: str | None = Query(default=None),
    plan_slug: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Paginated[AdminSubscriptionResponse]]:
    rows, total = await AdminService(db=db).list_subscriptions_paginated(
        status=status,
        plan_slug=plan_slug,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    items = [_sub_to_response(sub, plan) for sub, plan in rows]
    return ApiResponse.ok(
        Paginated[AdminSubscriptionResponse](
            data=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.patch(
    "/subscriptions/{subscription_id}/override",
    response_model=ApiResponse[AdminSubscriptionResponse],
)
async def override_subscription(
    subscription_id: uuid.UUID,
    payload: AdminSubscriptionOverrideRequest,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminSubscriptionResponse]:
    sub, plan = await AdminService(db=db).override_subscription(
        subscription_id, payload, uuid.UUID(admin.sub)
    )
    return ApiResponse.ok(_sub_to_response(sub, plan))


# ---------------------------------------------------------------------------
# AI Costs
# ---------------------------------------------------------------------------


@router.get("/ai-costs", response_model=ApiResponse[AdminAiCostPagedResponse])
async def list_ai_costs(
    _: AdminUser,
    db: DBSession,
    ai_module: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    sort_by: str = Query(default="occurred_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[AdminAiCostPagedResponse]:
    svc = AdminService(db=db)
    records, total = await svc.list_ai_costs_paginated(
        ai_module=ai_module,
        from_date=from_date,
        to_date=to_date,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    totals = await svc.get_ai_cost_totals(
        ai_module=ai_module,
        from_date=from_date,
        to_date=to_date,
    )
    return ApiResponse.ok(
        AdminAiCostPagedResponse(
            data=[AdminAiCostResponse.model_validate(r) for r in records],
            total=total,
            page=page,
            page_size=page_size,
            totals=AdminAiCostTotals(**totals),
        )
    )


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


@router.get("/audit-logs", response_model=ApiResponse[Paginated[AdminAuditLogResponse]])
async def list_audit_logs(
    _: AdminUser,
    db: DBSession,
    event_type: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    sort_by: str = Query(default="occurred_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Paginated[AdminAuditLogResponse]]:
    logs, total = await AdminService(db=db).list_audit_logs_paginated(
        event_type=event_type,
        target_type=target_type,
        from_date=from_date,
        to_date=to_date,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return ApiResponse.ok(
        Paginated[AdminAuditLogResponse](
            data=[AdminAuditLogResponse.model_validate(e) for e in logs],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=ApiResponse[list[AdminTemplateResponse]])
async def list_templates(
    _: AdminUser,
    db: DBSession,
    template_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> ApiResponse[list[AdminTemplateResponse]]:
    templates = await AdminService(db=db).list_templates(
        template_type=template_type,
        is_active=is_active,
    )
    return ApiResponse.ok([AdminTemplateResponse.model_validate(t) for t in templates])


@router.post("/templates", response_model=ApiResponse[AdminTemplateResponse], status_code=201)
async def create_template(
    payload: AdminCreateTemplateRequest,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminTemplateResponse]:
    template = await AdminService(db=db).create_template(
        payload, admin_id=uuid.UUID(admin.sub)
    )
    return ApiResponse.created(AdminTemplateResponse.model_validate(template))


@router.patch("/templates/{template_id}", response_model=ApiResponse[AdminTemplateResponse])
async def update_template(
    template_id: uuid.UUID,
    payload: AdminUpdateTemplateRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminTemplateResponse]:
    template = await AdminService(db=db).update_template(template_id, payload)
    return ApiResponse.ok(AdminTemplateResponse.model_validate(template))


# ---------------------------------------------------------------------------
# Feature Flags
# ---------------------------------------------------------------------------


@router.get("/feature-flags", response_model=ApiResponse[list[AdminFeatureFlagResponse]])
async def list_feature_flags(
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[list[AdminFeatureFlagResponse]]:
    flags = await AdminService(db=db).list_feature_flags()
    return ApiResponse.ok([AdminFeatureFlagResponse.model_validate(f) for f in flags])


@router.patch(
    "/feature-flags/{flag_name}", response_model=ApiResponse[AdminFeatureFlagResponse]
)
async def update_feature_flag(
    flag_name: str,
    payload: AdminUpdateFeatureFlagRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminFeatureFlagResponse]:
    flag = await AdminService(db=db).update_feature_flag(flag_name, payload)
    return ApiResponse.ok(AdminFeatureFlagResponse.model_validate(flag))


# ---------------------------------------------------------------------------
# Platform Metrics
# ---------------------------------------------------------------------------


@router.get("/platform-metrics", response_model=ApiResponse[AdminPlatformMetricsResponse])
async def get_platform_metrics(
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlatformMetricsResponse]:
    metrics = await AdminService(db=db).get_platform_metrics()
    return ApiResponse.ok(AdminPlatformMetricsResponse(**metrics))
