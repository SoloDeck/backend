#!/usr/bin/env python
"""Bootstrap the application: run migrations then seed.

Idempotent — safe to run on every deploy or container start.

Usage:
    python scripts/bootstrap.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings
from src.infrastructure.database.seeders.run import run_all

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


def _run_migrations() -> None:
    root = Path(__file__).parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


async def _seed(db_url: str) -> None:
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await run_all(session)
    await engine.dispose()


async def main() -> None:
    db_url = str(settings.database_url)
    log = logger.bind(env=settings.app_env, db=db_url.split("@")[-1])

    log.info("bootstrap.migrate_start")
    _run_migrations()
    log.info("bootstrap.migrate_done")

    log.info("bootstrap.seed_start")
    await _seed(db_url)
    log.info("bootstrap.seed_done")

    log.info("bootstrap.complete")


if __name__ == "__main__":
    asyncio.run(main())
