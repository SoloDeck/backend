"""Admin application service."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import PlanModel, SubscriptionModel, UserModel
from src.modules.admin.infrastructure.repository import AdminRepository
from src.modules.admin.schemas.request import (
    AdminCreateTemplateRequest,
    AdminPlanRequest,
    AdminSubscriptionOverrideRequest,
    AdminUpdateFeatureFlagRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
)
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError


@dataclass
class AdminService:
    db: AsyncSession
    repo: AdminRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AdminRepository(self.db)

    # -------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------

    async def list_users(self) -> list:
        return await self.repo.list_users()

    async def list_users_paginated(
        self,
        *,
        status: str | None = None,
        role: str | None = None,
        search: str | None = None,
        plan_slug: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_users_paginated(
            status=status,
            role=role,
            search=search,
            plan_slug=plan_slug,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def get_user(self, user_id: uuid.UUID) -> UserModel:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def update_user(self, user_id: uuid.UUID, payload: AdminUpdateUserRequest) -> UserModel:
        user = await self.get_user(user_id)
        if payload.role is not None:
            user.role = payload.role
        if payload.status is not None:
            user.status = payload.status
        if payload.full_name is not None:
            user.full_name = payload.full_name
        return await self.repo.save(user)

    async def suspend_user(
        self, user_id: uuid.UUID, *, admin_id: uuid.UUID
    ) -> UserModel:
        user = await self.get_user(user_id)
        if user.role == "admin":
            active_admin_count = await self.repo.count_active_admins()
            if active_admin_count <= 1:
                raise BusinessRuleError("Cannot suspend the last active admin account")
        user.status = "suspended"
        user = await self.repo.save(user)
        await self.repo.create_audit_log(
            event_type="user.suspended",
            actor_user_id=admin_id,
            target_type="user",
            target_id=user_id,
            description=f"Admin suspended user {user.email}",
        )
        return user

    async def reinstate_user(
        self, user_id: uuid.UUID, *, admin_id: uuid.UUID
    ) -> UserModel:
        user = await self.get_user(user_id)
        user.status = "active"
        user = await self.repo.save(user)
        await self.repo.create_audit_log(
            event_type="user.reinstated",
            actor_user_id=admin_id,
            target_type="user",
            target_id=user_id,
            description=f"Admin reinstated user {user.email}",
        )
        return user

    async def revoke_user_sessions(self, user_id: uuid.UUID) -> None:
        tokens = await self.repo.get_user_refresh_tokens(user_id)
        for token in tokens:
            await self.repo.blacklist_refresh_token(
                jti=token.token_hash,
                user_id=user_id,
                expires_at=token.expires_at,
            )

    # -------------------------------------------------------------------------
    # Plans
    # -------------------------------------------------------------------------

    async def list_plans(self) -> list:
        return await self.repo.list_plans()

    async def create_plan(self, payload: AdminPlanRequest):
        return await self.repo.create_plan(
            name=payload.name,
            slug=payload.slug,
            price_monthly=payload.price_monthly,
            currency=payload.currency,
            can_use_ai=payload.can_use_ai,
            can_export_pdf=payload.can_export_pdf,
            max_clients=payload.max_clients,
            max_deals=payload.max_deals,
            max_ai_generations_per_month=payload.max_ai_generations_per_month,
            is_active=payload.is_active,
        )

    async def update_plan(self, plan_id: uuid.UUID, payload: AdminPlanRequest):
        plan = await self.repo.get_plan(plan_id)
        if plan is None:
            raise NotFoundError(f"Plan {plan_id} not found")
        plan.name = payload.name
        plan.slug = payload.slug
        plan.price_monthly = payload.price_monthly
        plan.currency = payload.currency
        plan.can_use_ai = payload.can_use_ai
        plan.can_export_pdf = payload.can_export_pdf
        plan.max_clients = payload.max_clients
        plan.max_deals = payload.max_deals
        plan.max_ai_generations_per_month = payload.max_ai_generations_per_month
        plan.is_active = payload.is_active
        return await self.repo.save(plan)

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    async def list_subscriptions_paginated(
        self,
        *,
        status: str | None = None,
        plan_slug: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[tuple], int]:
        return await self.repo.list_subscriptions_paginated(
            status=status,
            plan_slug=plan_slug,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def override_subscription(
        self,
        subscription_id: uuid.UUID,
        payload: AdminSubscriptionOverrideRequest,
        admin_id: uuid.UUID,
    ) -> tuple[SubscriptionModel, PlanModel]:
        sub = await self.repo.get_subscription(subscription_id)
        if sub is None:
            raise NotFoundError(f"Subscription {subscription_id} not found")
        if payload.plan_id is not None:
            sub.plan_id = payload.plan_id
        if payload.override_expires_at is not None:
            sub.override_expires_at = payload.override_expires_at
        sub.override_by_admin_id = admin_id
        sub = await self.repo.save(sub)
        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None:
            raise NotFoundError(f"Plan {sub.plan_id} not found")
        return sub, plan

    # -------------------------------------------------------------------------
    # Audit Logs
    # -------------------------------------------------------------------------

    async def list_audit_logs_paginated(
        self,
        *,
        event_type: str | None = None,
        target_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sort_by: str = "occurred_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_audit_logs_paginated(
            event_type=event_type,
            target_type=target_type,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    # -------------------------------------------------------------------------
    # AI Costs
    # -------------------------------------------------------------------------

    async def list_ai_costs_paginated(
        self,
        *,
        ai_module: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sort_by: str = "occurred_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_ai_costs_paginated(
            ai_module=ai_module,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def get_ai_cost_totals(
        self,
        *,
        ai_module: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict:
        return await self.repo.get_ai_cost_totals(
            ai_module=ai_module,
            from_date=from_date,
            to_date=to_date,
        )

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    async def list_templates(
        self,
        *,
        template_type: str | None = None,
        is_active: bool | None = None,
    ) -> list:
        return await self.repo.list_templates(
            template_type=template_type,
            is_active=is_active,
        )

    async def create_template(
        self,
        payload: AdminCreateTemplateRequest,
        *,
        admin_id: uuid.UUID,
    ):
        return await self.repo.create_template(
            name=payload.name,
            template_type=payload.template_type,
            content=payload.content,
            plan_tier_required=payload.plan_tier_required,
            is_active=payload.is_active,
            created_by_admin_id=admin_id,
        )

    async def update_template(
        self,
        template_id: uuid.UUID,
        payload: AdminUpdateTemplateRequest,
    ):
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")
        if payload.name is not None:
            template.name = payload.name
        if payload.content is not None:
            template.content = payload.content
            template.version_number = (template.version_number or 1) + 1
        if payload.is_active is not None:
            template.is_active = payload.is_active
        if payload.plan_tier_required is not None:
            template.plan_tier_required = payload.plan_tier_required
        return await self.repo.save(template)

    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------

    async def list_feature_flags(self) -> list:
        return await self.repo.list_feature_flags()

    async def update_feature_flag(
        self,
        flag_name: str,
        payload: AdminUpdateFeatureFlagRequest,
    ):
        flag = await self.repo.get_feature_flag_by_name(flag_name)
        if flag is None:
            raise NotFoundError(f"Feature flag '{flag_name}' not found")
        if payload.is_enabled is not None:
            flag.is_enabled = payload.is_enabled
        if payload.rollout_percentage is not None:
            flag.rollout_percentage = payload.rollout_percentage
        if payload.target_user_ids is not None:
            flag.target_user_ids = payload.target_user_ids
        if payload.description is not None:
            flag.description = payload.description
        return await self.repo.save(flag)

    # -------------------------------------------------------------------------
    # Platform Metrics
    # -------------------------------------------------------------------------

    async def get_platform_metrics(self) -> dict:
        return await self.repo.get_platform_metrics()
