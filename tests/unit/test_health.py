"""Liveness and readiness endpoints.

Readiness is what the container healthcheck probes, so its failure path matters
more than its happy path: a readiness endpoint that reports 200 while Postgres
is unreachable is exactly how a broken deploy stays invisible.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src import main


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _get(path: str):
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


class TestLiveness:
    async def test_returns_ok_without_touching_dependencies(self, monkeypatch) -> None:
        async def _boom() -> None:
            raise AssertionError("liveness must not probe dependencies")

        monkeypatch.setattr(main, "_probe_database", _boom)
        monkeypatch.setattr(main, "_probe_redis", _boom)

        resp = await _get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestReadiness:
    async def test_all_dependencies_up_returns_200(self, monkeypatch) -> None:
        async def _ok() -> None:
            return None

        monkeypatch.setattr(main, "_probe_database", _ok)
        monkeypatch.setattr(main, "_probe_redis", _ok)

        resp = await _get("/health/ready")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"] == {"database": "ok", "redis": "ok"}

    async def test_database_down_returns_503(self, monkeypatch) -> None:
        async def _ok() -> None:
            return None

        async def _fail() -> None:
            raise ConnectionRefusedError("no route to postgres")

        monkeypatch.setattr(main, "_probe_database", _fail)
        monkeypatch.setattr(main, "_probe_redis", _ok)

        resp = await _get("/health/ready")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["database"].startswith("fail: ConnectionRefusedError")
        assert body["checks"]["redis"] == "ok"

    async def test_redis_down_returns_503(self, monkeypatch) -> None:
        async def _ok() -> None:
            return None

        async def _fail() -> None:
            raise TimeoutError("redis ping timed out")

        monkeypatch.setattr(main, "_probe_database", _ok)
        monkeypatch.setattr(main, "_probe_redis", _fail)

        resp = await _get("/health/ready")

        assert resp.status_code == 503
        assert resp.json()["checks"]["redis"].startswith("fail: TimeoutError")

    async def test_reports_every_failing_dependency(self, monkeypatch) -> None:
        async def _fail() -> None:
            raise OSError("network unreachable")

        monkeypatch.setattr(main, "_probe_database", _fail)
        monkeypatch.setattr(main, "_probe_redis", _fail)

        resp = await _get("/health/ready")

        assert resp.status_code == 503
        checks = resp.json()["checks"]
        assert checks["database"].startswith("fail: OSError")
        assert checks["redis"].startswith("fail: OSError")
