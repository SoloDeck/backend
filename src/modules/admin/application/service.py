"""Admin application service."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.admin.infrastructure.repository import AdminRepository
from src.modules.admin.schemas.request import AdminPlanRequest, AdminUpdateUserRequest
from src.shared.exceptions.domain import NotFoundError


@dataclass
class AdminService:
    db: AsyncSession
    repo: AdminRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AdminRepository(self.db)

    async def list_users(self) -> list:
        return await self.repo.list_users()

    async def get_user(self, user_id: uuid.UUID):  # type: ignore[return]
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def update_user(self, user_id: uuid.UUID, payload: AdminUpdateUserRequest):  # type: ignore[return]
        user = await self.get_user(user_id)
        if payload.role is not None:
            user.role = payload.role
        if payload.status is not None:
            user.status = payload.status
        if payload.full_name is not None:
            user.full_name = payload.full_name
        return await self.repo.save(user)

    async def list_plans(self) -> list:
        return await self.repo.list_plans()

    async def create_plan(self, payload: AdminPlanRequest):  # type: ignore[return]
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

    async def update_plan(self, plan_id: uuid.UUID, payload: AdminPlanRequest):  # type: ignore[return]
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
