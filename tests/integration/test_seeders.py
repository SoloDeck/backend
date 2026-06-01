"""Integration tests for seeder infrastructure.

These tests require a real PostgreSQL database created by `create_tables`
in conftest.py.  They do NOT use Alembic migrations — the schema is created
directly from SQLAlchemy metadata (Base.metadata.create_all).

Test coverage:
- PlansSeeder creates the three canonical plans
- PlansSeeder is idempotent (double run produces no duplicates)
- AdminSeeder creates an admin user in development
- AdminSeeder is idempotent (double run produces no duplicates)
- run_all honours APP_ENV guard (admin skipped outside development)
- Default plan slugs: free, pro, business
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import PlanModel, UserModel
from src.infrastructure.database.seeders.admin import ADMIN_EMAIL, AdminSeeder
from src.infrastructure.database.seeders.plans import PlansSeeder
from src.infrastructure.database.seeders.run import run_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _plan_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(PlanModel))
    return result.scalar_one()


async def _plan_slugs(db: AsyncSession) -> set[str]:
    result = await db.execute(select(PlanModel.slug))
    return {row[0] for row in result.all()}


async def _user_by_email(db: AsyncSession, email: str) -> UserModel | None:
    return await db.scalar(select(UserModel).where(UserModel.email == email))


# ---------------------------------------------------------------------------
# PlansSeeder
# ---------------------------------------------------------------------------

class TestPlansSeeder:
    async def test_creates_three_plans(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        assert await _plan_count(db_session) == 3

    async def test_creates_expected_slugs(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        slugs = await _plan_slugs(db_session)
        assert slugs == {"free", "pro", "business"}

    async def test_free_plan_has_no_ai(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        free = await db_session.scalar(select(PlanModel).where(PlanModel.slug == "free"))
        assert free is not None
        assert free.can_use_ai is False
        assert free.can_export_pdf is False

    async def test_pro_plan_has_ai(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        pro = await db_session.scalar(select(PlanModel).where(PlanModel.slug == "pro"))
        assert pro is not None
        assert pro.can_use_ai is True
        assert pro.max_ai_generations_per_month == 50

    async def test_business_plan_has_most_ai(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        biz = await db_session.scalar(
            select(PlanModel).where(PlanModel.slug == "business")
        )
        assert biz is not None
        assert biz.can_use_ai is True
        assert biz.max_ai_generations_per_month == 500

    async def test_idempotent_no_duplicates(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        await PlansSeeder(db_session).run()
        assert await _plan_count(db_session) == 3

    async def test_idempotent_three_times(self, db_session: AsyncSession) -> None:
        for _ in range(3):
            await PlansSeeder(db_session).run()
        assert await _plan_count(db_session) == 3

    async def test_free_plan_limits(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        free = await db_session.scalar(select(PlanModel).where(PlanModel.slug == "free"))
        assert free is not None
        assert free.max_clients == 10
        assert free.max_deals == 10

    async def test_pro_plan_unlimited(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        pro = await db_session.scalar(select(PlanModel).where(PlanModel.slug == "pro"))
        assert pro is not None
        assert pro.max_clients is None
        assert pro.max_deals is None


# ---------------------------------------------------------------------------
# AdminSeeder
# ---------------------------------------------------------------------------

class TestAdminSeeder:
    async def test_creates_admin_user(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        await AdminSeeder(db_session).run()
        admin = await _user_by_email(db_session, ADMIN_EMAIL)
        assert admin is not None
        assert admin.role == "admin"
        assert admin.status == "active"

    async def test_admin_has_hashed_password(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        await AdminSeeder(db_session).run()
        admin = await _user_by_email(db_session, ADMIN_EMAIL)
        assert admin is not None
        assert admin.hashed_password is not None
        assert admin.hashed_password != "Admin@SoloDesk2025!"

    async def test_idempotent_no_duplicates(self, db_session: AsyncSession) -> None:
        await PlansSeeder(db_session).run()
        await AdminSeeder(db_session).run()
        await AdminSeeder(db_session).run()
        result = await db_session.execute(
            select(func.count()).select_from(UserModel).where(
                UserModel.email == ADMIN_EMAIL
            )
        )
        assert result.scalar_one() == 1


# ---------------------------------------------------------------------------
# run_all — environment guard
# ---------------------------------------------------------------------------

class TestRunAll:
    async def test_seeds_plans_in_production(self, db_session: AsyncSession) -> None:
        with patch("src.infrastructure.database.seeders.run.settings") as mock_settings:
            mock_settings.app_env = "production"
            await run_all(db_session)
        assert await _plan_count(db_session) == 3

    async def test_skips_admin_outside_development(self, db_session: AsyncSession) -> None:
        with patch("src.infrastructure.database.seeders.run.settings") as mock_settings:
            mock_settings.app_env = "staging"
            await run_all(db_session)
        admin = await _user_by_email(db_session, ADMIN_EMAIL)
        assert admin is None

    async def test_seeds_admin_in_development(self, db_session: AsyncSession) -> None:
        with patch("src.infrastructure.database.seeders.run.settings") as mock_settings:
            mock_settings.app_env = "development"
            await run_all(db_session)
        admin = await _user_by_email(db_session, ADMIN_EMAIL)
        assert admin is not None

    async def test_run_all_idempotent(self, db_session: AsyncSession) -> None:
        with patch("src.infrastructure.database.seeders.run.settings") as mock_settings:
            mock_settings.app_env = "development"
            await run_all(db_session)
            await run_all(db_session)
        assert await _plan_count(db_session) == 3
        result = await db_session.execute(
            select(func.count()).select_from(UserModel).where(
                UserModel.email == ADMIN_EMAIL
            )
        )
        assert result.scalar_one() == 1
