#!/usr/bin/env python
"""Run all seeders against the configured database.

Usage:
    python scripts/seed.py

Reads DATABASE_URL (and APP_ENV) from environment / .env file.
Safe to run multiple times — all seeders are idempotent.
"""

import asyncio
import sys
from pathlib import Path

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
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


async def main() -> None:
    log = logger.bind(database_url=str(settings.database_url).split("@")[-1])
    log.info("seed.start")

    engine = create_async_engine(str(settings.database_url), echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with factory() as session:
            await run_all(session)
    finally:
        await engine.dispose()

    log.info("seed.complete")


if __name__ == "__main__":
    asyncio.run(main())
