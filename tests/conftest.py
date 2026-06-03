"""Shared test fixtures.

Uses a real PostgreSQL test database (not mocked) to catch migration/query issues.
Set TEST_DATABASE_URL in environment or .env.test before running tests.

DATABASE_URL must also point at the test database so that alembic/env.py and the
FastAPI app under test both use the same connection. The test service in
docker-compose.yml sets both variables to the same value.

Session isolation strategy
--------------------------
Services call session.commit() to persist data. To keep tests isolated we use
the SQLAlchemy "outer connection + savepoint" pattern:

  outer transaction
  └─ savepoint  ←── session.commit() lands here (not real DB commit)
      └─ test body
  rollback outer ←── undoes everything after the test

This requires join_transaction_mode="create_savepoint" on the AsyncSession
and NullPool so each test gets a dedicated connection with no pool reuse.
"""

import asyncio
import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path

# ── Resolve test DB URL ────────────────────────────────────────────────────────
# Must happen BEFORE any src/ import so that pydantic-settings reads the right
# DATABASE_URL when it initialises the Settings singleton.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://solodesk:solodesk@localhost:5432/solodesk_test",
)
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

# ── src imports (settings singleton initialised here with DATABASE_URL above) ──
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import src.infrastructure.database.models  # noqa: F401 — registers all ORM models with Base
from src.infrastructure.database.session import get_db_session
from src.main import app


# ── Helpers that run once at import time (before the event loop starts) ────────


def _ensure_test_db() -> None:
    """Create solodesk_test database if it doesn't already exist."""
    match = re.match(
        r"postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:/]+):?(\d*)/(.+)",
        TEST_DATABASE_URL,
    )
    if not match:
        return
    user, password, host, port_str, db_name = match.groups()
    port = int(port_str) if port_str else 5432

    async def _create() -> None:
        import asyncpg

        conn = await asyncpg.connect(
            user=user, password=password, host=host, port=port, database="postgres"
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db_name
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

    asyncio.run(_create())


def _run_migrations() -> None:
    """Apply Alembic migrations to the test DB (idempotent).

    alembic/env.py reads DATABASE_URL via settings — which was already pointed
    at the test DB before the settings singleton was created (see top of file).
    """
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


_ensure_test_db()
_run_migrations()


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test isolated session using outer-transaction + savepoint pattern.

    NullPool ensures each test gets a fresh connection with no pool contamination.
    join_transaction_mode="create_savepoint" means session.commit() commits to
    the savepoint, not the real DB. The outer rollback undoes everything.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
        )
        yield session
        await session.close()
        await conn.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()
