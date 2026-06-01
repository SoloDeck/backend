"""Seeder orchestrator — runs all seeders in dependency order."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings

from .admin import AdminSeeder
from .plans import PlansSeeder

logger = structlog.get_logger(__name__)


async def run_all(db: AsyncSession) -> None:
    """Run all seeders in dependency order.

    Safe to call multiple times — every seeder is idempotent.
    """
    log = logger.bind(env=settings.app_env)
    log.info("seeders.start")

    await PlansSeeder(db).run()

    if settings.app_env == "development":
        await AdminSeeder(db).run()

    log.info("seeders.done")
