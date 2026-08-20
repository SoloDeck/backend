"""Admin API router."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.admin.application.service import AdminService
from src.modules.admin.application.template_preview import render_template_preview
from src.modules.admin.schemas.request import (
    AdminCreateTemplateRequest,
    AdminPlanRequest,
    AdminSubscriptionOverrideRequest,
    AdminUpdateFeatureFlagRequest,
    AdminUpdateLLMProviderRequest,
    AdminUpdatePlanRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
)
from src.modules.admin.schemas.response import (
    AdminAiCostPagedResponse,
    AdminAiCostResponse,
    AdminAiCostTotals,
    AdminAuditLogResponse,
    AdminFeatureFlagResponse,
    AdminLLMProviderResponse,
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
    status: Literal["active", "suspended", "deleted"] | None = Query(default=None),
    role: Literal["freelancer", "admin"] | None = Query(default=None),
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
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminUserResponse]:
    user = await AdminService(db=db).update_user(
        user_id, payload, admin_id=uuid.UUID(admin.sub)
    )
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
    admin: AdminUser,
    db: DBSession,
) -> Response:
    await AdminService(db=db).revoke_user_sessions(user_id, admin_id=uuid.UUID(admin.sub))
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


@router.get("/plans/{plan_id}", response_model=ApiResponse[AdminPlanResponse])
async def get_plan(
    plan_id: uuid.UUID,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlanResponse]:
    plan = await AdminService(db=db).get_plan(plan_id)
    return ApiResponse.ok(AdminPlanResponse.model_validate(plan))


@router.post("/plans", response_model=ApiResponse[AdminPlanResponse], status_code=201)
async def create_plan(
    payload: AdminPlanRequest,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlanResponse]:
    plan = await AdminService(db=db).create_plan(payload, admin_id=uuid.UUID(admin.sub))
    return ApiResponse.created(AdminPlanResponse.model_validate(plan))


@router.patch("/plans/{plan_id}", response_model=ApiResponse[AdminPlanResponse])
async def update_plan(
    plan_id: uuid.UUID,
    payload: AdminUpdatePlanRequest,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminPlanResponse]:
    plan = await AdminService(db=db).update_plan(
        plan_id, payload, admin_id=uuid.UUID(admin.sub)
    )
    return ApiResponse.ok(AdminPlanResponse.model_validate(plan))


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: uuid.UUID,
    admin: AdminUser,
    db: DBSession,
) -> None:
    """Xoá hẳn một gói chưa từng được dùng. Gói đã có người dùng → 409, kèm lý do và
    hướng dẫn ngừng bán thay vì xoá."""
    await AdminService(db=db).delete_plan(plan_id, admin_id=uuid.UUID(admin.sub))


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@router.get("/subscriptions", response_model=ApiResponse[Paginated[AdminSubscriptionResponse]])
async def list_subscriptions(
    _: AdminUser,
    db: DBSession,
    status: Literal["active", "past_due", "suspended", "cancelled"] | None = Query(default=None),
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
    ai_module: (
        Literal["lead_qualifier", "proposal_generator", "contract_generator", "followup_generator"]
        | None
    ) = Query(default=None),
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
            # Mỗi bản ghi là (record, email, full_name) do repo join users → biết ai gen AI.
            data=[
                AdminAiCostResponse(
                    id=r.id,
                    user_id=r.user_id,
                    user_email=email,
                    user_full_name=full_name,
                    ai_module=r.ai_module,
                    model_used=r.model_used,
                    input_tokens=r.input_tokens,
                    output_tokens=r.output_tokens,
                    estimated_cost_usd=r.estimated_cost_usd,
                    status=r.status,
                    occurred_at=r.occurred_at,
                )
                for (r, email, full_name) in records
            ],
            total=total,
            page=page,
            page_size=page_size,
            totals=AdminAiCostTotals(**totals),
        )
    )

# ---------------------------------------------------------------------------
# AI Provider Configuration
# ---------------------------------------------------------------------------

@router.get(
    "/ai-provider",
    response_model=ApiResponse[AdminLLMProviderResponse],
)
async def get_ai_provider(
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminLLMProviderResponse]:

    configuration = await (
        AdminService(db=db)
        .get_ai_provider_configuration()
    )

    return ApiResponse.ok(
        AdminLLMProviderResponse(
            llm_provider=configuration.llm_provider,
            llm_model=configuration.llm_model,
        )
    )


@router.patch(
    "/ai-provider",
    response_model=ApiResponse[AdminLLMProviderResponse],
)
async def update_ai_provider(
    payload: AdminUpdateLLMProviderRequest,
    admin: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminLLMProviderResponse]:

    configuration = await (
        AdminService(db=db)
        .update_ai_provider_configuration(
            llm_provider=payload.llm_provider,
            llm_model=payload.llm_model,
            admin_id=uuid.UUID(admin.sub),
        )
    )

    return ApiResponse.ok(
        AdminLLMProviderResponse(
            llm_provider=configuration.llm_provider,
            llm_model=configuration.llm_model,
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
            # Mỗi bản ghi là (entry, actor_email, actor_full_name) do repo join users.
            data=[
                AdminAuditLogResponse(
                    id=e.id,
                    event_type=e.event_type,
                    actor_user_id=e.actor_user_id,
                    actor_email=actor_email,
                    actor_full_name=actor_full_name,
                    target_type=e.target_type,
                    target_id=e.target_id,
                    description=e.description,
                    occurred_at=e.occurred_at,
                )
                for (e, actor_email, actor_full_name) in logs
            ],
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
    template_type: Literal["proposal", "contract"] | None = Query(default=None),
    profession: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
) -> ApiResponse[list[AdminTemplateResponse]]:
    templates = await AdminService(db=db).list_templates(
        template_type=template_type,
        profession=profession,
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


class TemplatePreviewRequest(BaseModel):
    template_type: Literal["proposal", "contract"] = "proposal"
    content: dict = {}


class TemplatePreviewResponse(BaseModel):
    html: str


@router.post("/templates/preview", response_model=ApiResponse[TemplatePreviewResponse])
async def preview_template(
    payload: TemplatePreviewRequest,
    _: AdminUser,
) -> ApiResponse[TemplatePreviewResponse]:
    """Dựng TỜ GIẤY THẬT từ nội dung mẫu — để admin soạn mà nhìn thấy ngay kết quả.

    Nhận `content` thẳng từ màn soạn chứ không đọc DB: admin cần thấy bản đang gõ dở, trước cả
    khi bấm Lưu. Vì vậy endpoint này KHÔNG chạm database và không cần `template_id`.

    Cùng một template Jinja với bản freelancer nhận và với PDF, nên cái admin thấy đúng là cái
    khách sẽ đọc — không có đường nào để hai bên lệch nhau.  #Huynh
    """
    html = render_template_preview(payload.template_type, payload.content)
    return ApiResponse.ok(TemplatePreviewResponse(html=html))


@router.patch("/templates/{template_id}", response_model=ApiResponse[AdminTemplateResponse])
async def update_template(
    template_id: uuid.UUID,
    payload: AdminUpdateTemplateRequest,
    _: AdminUser,
    db: DBSession,
) -> ApiResponse[AdminTemplateResponse]:
    template = await AdminService(db=db).update_template(template_id, payload)
    return ApiResponse.ok(AdminTemplateResponse.model_validate(template))


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    admin: AdminUser,
    db: DBSession,
) -> None:
    """Xoá một mẫu hệ thống khỏi thư viện.

    Đề xuất/hợp đồng đã tạo từ mẫu không bị ảnh hưởng (nội dung đã được sao chép sang).
    Chỉ chặn khi còn mẫu phái sinh trỏ vào mẫu này — khi đó trả 409.
    """
    await AdminService(db=db).delete_template(template_id, admin_id=uuid.UUID(admin.sub))


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
