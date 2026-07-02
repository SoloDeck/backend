import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.infrastructure.database.models import (
    AiCostRecordModel,
    AuditLogEntryModel,
    ClientModel,
    DealModel,
    FeatureFlagModel,
    PlanModel,
    RefreshTokenModel,
    SubscriptionModel,
    SystemTemplateModel,
    TokenBlacklistModel,
    UserModel,
)

_USER_SORT_COLS = {
    "created_at": UserModel.created_at,
    "email": UserModel.email,
    "full_name": UserModel.full_name,
    "status": UserModel.status,
}

_SUB_SORT_COLS = {
    "created_at": SubscriptionModel.created_at,
}

_AUDIT_SORT_COLS = {
    "occurred_at": AuditLogEntryModel.occurred_at,
}

_AI_SORT_COLS = {
    "occurred_at": AiCostRecordModel.occurred_at,
}


@dataclass
class AdminRepository:
    db: AsyncSession

    # -------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------

    async def list_users(self) -> list:
        result = await self.db.execute(select(UserModel).where(UserModel.deleted_at.is_(None)))
        return list(result.scalars().all())

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
        filters = [UserModel.deleted_at.is_(None)]
        if status is not None:
            filters.append(UserModel.status == status)
        if role is not None:
            filters.append(UserModel.role == role)
        if search is not None:
            filters.append(
                or_(
                    UserModel.email.ilike(f"%{search}%"),
                    UserModel.full_name.ilike(f"%{search}%"),
                )
            )

        if plan_slug is not None:
            base_q = (
                select(UserModel)
                .join(SubscriptionModel, SubscriptionModel.user_id == UserModel.id)
                .join(PlanModel, PlanModel.id == SubscriptionModel.plan_id)
                .where(*filters, PlanModel.slug == plan_slug)
            )
        else:
            base_q = select(UserModel).where(*filters)

        total = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        sort_col = _USER_SORT_COLS.get(sort_by, UserModel.created_at)
        ordered = sort_col.desc() if sort_order == "desc" else sort_col.asc()
        data_q = (
            base_q.options(selectinload(UserModel.subscription).selectinload(SubscriptionModel.plan))
            .order_by(ordered)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(data_q)
        return list(result.scalars().all()), total

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel)
            .where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
            .options(selectinload(UserModel.subscription).selectinload(SubscriptionModel.plan))
        )

    async def get_user_by_email(self, email: str, *, exclude_user_id: uuid.UUID | None = None):
        stmt = select(UserModel).where(
            UserModel.email == email,
            UserModel.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return await self.db.scalar(stmt)

    async def get_user_by_phone(self, phone: str, *, exclude_user_id: uuid.UUID | None = None):
        stmt = select(UserModel).where(
            UserModel.phone == phone,
            UserModel.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return await self.db.scalar(stmt)

    async def count_active_admins(self) -> int:
        return await self.db.scalar(
            select(func.count(UserModel.id)).where(
                UserModel.role == "admin",
                UserModel.status != "suspended",
                UserModel.deleted_at.is_(None),
            )
        ) or 0

    async def get_user_refresh_tokens(self, user_id: uuid.UUID) -> list:
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.expires_at > now,
                RefreshTokenModel.revoked_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def blacklist_refresh_token(
        self, jti: str, user_id: uuid.UUID, expires_at: datetime
    ) -> None:
        stmt = (
            pg_insert(TokenBlacklistModel)
            .values(jti=jti, user_id=user_id, expires_at=expires_at)
            .on_conflict_do_nothing(index_elements=["jti"])
        )
        await self.db.execute(stmt)

    # -------------------------------------------------------------------------
    # Plans
    # -------------------------------------------------------------------------

    async def list_plans(self) -> list:
        result = await self.db.execute(select(PlanModel))
        return list(result.scalars().all())

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def create_plan(self, **values):
        plan = PlanModel(**values)
        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)
        return plan

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
        base_q = select(SubscriptionModel, PlanModel).join(
            PlanModel, SubscriptionModel.plan_id == PlanModel.id
        )
        if status is not None:
            base_q = base_q.where(SubscriptionModel.status == status)
        if plan_slug is not None:
            base_q = base_q.where(PlanModel.slug == plan_slug)

        total = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        sort_col = _SUB_SORT_COLS.get(sort_by, SubscriptionModel.created_at)
        ordered = sort_col.desc() if sort_order == "desc" else sort_col.asc()
        data_q = base_q.order_by(ordered).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(data_q)
        return list(result.all()), total

    async def get_subscription(self, subscription_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.id == subscription_id)
        )

    # -------------------------------------------------------------------------
    # Audit Logs
    # -------------------------------------------------------------------------

    async def create_audit_log(
        self,
        *,
        event_type: str,
        actor_user_id: uuid.UUID | None,
        target_type: str | None,
        target_id: uuid.UUID | None,
        description: str,
    ) -> None:
        entry = AuditLogEntryModel(
            event_type=event_type,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            description=description,
        )
        self.db.add(entry)

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
        base_q = select(AuditLogEntryModel)
        if event_type is not None:
            base_q = base_q.where(AuditLogEntryModel.event_type == event_type)
        if target_type is not None:
            base_q = base_q.where(AuditLogEntryModel.target_type == target_type)
        if from_date is not None:
            base_q = base_q.where(AuditLogEntryModel.occurred_at >= from_date)
        if to_date is not None:
            base_q = base_q.where(AuditLogEntryModel.occurred_at <= to_date)

        total = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        sort_col = _AUDIT_SORT_COLS.get(sort_by, AuditLogEntryModel.occurred_at)
        ordered = sort_col.desc() if sort_order == "desc" else sort_col.asc()
        data_q = base_q.order_by(ordered).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(data_q)
        return list(result.scalars().all()), total

    # -------------------------------------------------------------------------
    # AI Cost Records
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
        base_q = select(AiCostRecordModel)
        if ai_module is not None:
            base_q = base_q.where(AiCostRecordModel.ai_module == ai_module)
        if from_date is not None:
            base_q = base_q.where(AiCostRecordModel.occurred_at >= from_date)
        if to_date is not None:
            base_q = base_q.where(AiCostRecordModel.occurred_at <= to_date)

        total = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        sort_col = _AI_SORT_COLS.get(sort_by, AiCostRecordModel.occurred_at)
        ordered = sort_col.desc() if sort_order == "desc" else sort_col.asc()
        data_q = base_q.order_by(ordered).offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(data_q)
        return list(result.scalars().all()), total

    async def get_ai_cost_totals(
        self,
        *,
        ai_module: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict:
        agg_q = select(
            func.coalesce(func.sum(AiCostRecordModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AiCostRecordModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(
                func.sum(AiCostRecordModel.estimated_cost_usd), Decimal("0")
            ).label("estimated_cost_usd"),
        )
        if ai_module is not None:
            agg_q = agg_q.where(AiCostRecordModel.ai_module == ai_module)
        if from_date is not None:
            agg_q = agg_q.where(AiCostRecordModel.occurred_at >= from_date)
        if to_date is not None:
            agg_q = agg_q.where(AiCostRecordModel.occurred_at <= to_date)

        row = (await self.db.execute(agg_q)).one()
        return {
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "estimated_cost_usd": Decimal(str(row.estimated_cost_usd)),
        }

    # -------------------------------------------------------------------------
    # System Templates
    # -------------------------------------------------------------------------

    async def list_templates(
        self,
        *,
        template_type: str | None = None,
        is_active: bool | None = None,
    ) -> list:
        q = select(SystemTemplateModel)
        if template_type is not None:
            q = q.where(SystemTemplateModel.template_type == template_type)
        if is_active is not None:
            q = q.where(SystemTemplateModel.is_active == is_active)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def create_template(self, **values) -> SystemTemplateModel:
        template = SystemTemplateModel(**values)
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_template(self, template_id: uuid.UUID):
        return await self.db.scalar(
            select(SystemTemplateModel).where(SystemTemplateModel.id == template_id)
        )

    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------

    async def list_feature_flags(self) -> list:
        result = await self.db.execute(select(FeatureFlagModel))
        return list(result.scalars().all())

    async def get_feature_flag_by_name(self, flag_name: str):
        return await self.db.scalar(
            select(FeatureFlagModel).where(FeatureFlagModel.flag_name == flag_name)
        )

    # -------------------------------------------------------------------------
    # Platform Metrics
    # -------------------------------------------------------------------------

    async def get_platform_metrics(self) -> dict:
        now = datetime.now(UTC)
        thirty_days_ago = now - timedelta(days=30)

        total_users = await self.db.scalar(
            select(func.count(UserModel.id)).where(UserModel.deleted_at.is_(None))
        ) or 0

        active_users = await self.db.scalar(
            select(func.count(UserModel.id)).where(
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
        ) or 0

        suspended_users = await self.db.scalar(
            select(func.count(UserModel.id)).where(UserModel.status == "suspended")
        ) or 0

        total_subscriptions = await self.db.scalar(
            select(func.count(SubscriptionModel.id))
        ) or 0

        active_subscriptions = await self.db.scalar(
            select(func.count(SubscriptionModel.id)).where(
                SubscriptionModel.status == "active"
            )
        ) or 0

        total_plans = await self.db.scalar(select(func.count(PlanModel.id))) or 0

        active_plans = await self.db.scalar(
            select(func.count(PlanModel.id)).where(PlanModel.is_active.is_(True))
        ) or 0

        total_deals = await self.db.scalar(
            select(func.count(DealModel.id)).where(DealModel.deleted_at.is_(None))
        ) or 0

        total_clients = await self.db.scalar(
            select(func.count(ClientModel.id)).where(ClientModel.deleted_at.is_(None))
        ) or 0

        ai_cost_raw = await self.db.scalar(
            select(func.sum(AiCostRecordModel.estimated_cost_usd)).where(
                AiCostRecordModel.occurred_at >= thirty_days_ago
            )
        )
        ai_cost_last_30_days = Decimal(str(ai_cost_raw)) if ai_cost_raw is not None else Decimal("0")

        return {
            "total_users": total_users,
            "active_users": active_users,
            "suspended_users": suspended_users,
            "total_subscriptions": total_subscriptions,
            "active_subscriptions": active_subscriptions,
            "total_plans": total_plans,
            "active_plans": active_plans,
            "total_deals": total_deals,
            "total_clients": total_clients,
            "ai_cost_last_30_days": ai_cost_last_30_days,
        }

    # -------------------------------------------------------------------------
    # Generic
    # -------------------------------------------------------------------------

    async def save(self, obj):
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
