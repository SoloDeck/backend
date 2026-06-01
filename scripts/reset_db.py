#!/usr/bin/env python
"""Drop all tables, re-run migrations, and re-seed.

DESTRUCTIVE — development / CI only.
Refuses to run in production.

Usage:
    python scripts/reset_db.py [--no-seed]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import text
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

_BLOCKED_ENVS = ("production", "staging")


async def _drop_all(db_url: str) -> None:
    """Drop every user-created table and enum using CASCADE."""
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        # Terminate other connections so we can drop objects cleanly
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                " WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        )
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO PUBLIC"))
    await engine.dispose()


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


async def main(no_seed: bool = False) -> None:
    if settings.app_env in _BLOCKED_ENVS:
        logger.error(
            "reset_db.blocked",
            env=settings.app_env,
            reason="reset_db refuses to run in production/staging",
        )
        sys.exit(1)

    db_url = str(settings.database_url)
    log = logger.bind(env=settings.app_env, db=db_url.split("@")[-1])

    log.info("reset_db.drop_start")
    await _drop_all(db_url)
    log.info("reset_db.drop_done")

    log.info("reset_db.migrate_start")
    _run_migrations()
    log.info("reset_db.migrate_done")

    if not no_seed:
        log.info("reset_db.seed_start")
        await _seed(db_url)
        log.info("reset_db.seed_done")

    log.info("reset_db.complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drop, migrate, and re-seed the database")
    parser.add_argument(
        "--no-seed", action="store_true", help="Skip seeding after migration"
    )
    args = parser.parse_args()
    asyncio.run(main(no_seed=args.no_seed))
