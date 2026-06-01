#!/usr/bin/env python
"""Bootstrap the application: run migrations then seed.

Idempotent — safe to run on every deploy or container start.

Usage:
    python scripts/bootstrap.py

Design note:
    Alembic's async env.py calls asyncio.run() internally when applying
    migrations.  Therefore _run_migrations() must be called at the top
    level with no event loop active — never from inside asyncio.run().
    Seeders are async, so they run in a separate asyncio.run() call after
    migrations complete.
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
    """Run Alembic migrations synchronously.

    Must be called with no active event loop.  Alembic's async env.py
    calls asyncio.run() itself; nesting that inside another asyncio.run()
    raises RuntimeError.
    """
    root = Path(__file__).parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


async def _run_seeders() -> None:
    db_url = str(settings.database_url)
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await run_all(session)
    await engine.dispose()


def main() -> None:
    log = logger.bind(env=settings.app_env)

    log.info("bootstrap.migrate_start")
    _run_migrations()
    log.info("bootstrap.migrate_done")

    log.info("bootstrap.seed_start")
    asyncio.run(_run_seeders())
    log.info("bootstrap.seed_done")

    log.info("bootstrap.complete")


if __name__ == "__main__":
    main()
