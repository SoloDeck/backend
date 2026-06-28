"""Tests for request-id + access-log middleware."""

import re

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.shared.logging.context import get_request_id
from src.shared.logging.middleware import (
    AccessLogMiddleware,
    RequestContextMiddleware,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    # Context middleware added last → outermost → id bound before access log runs.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRequestContextMiddleware:
    async def test_generates_request_id_header_when_absent(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/ping")
        assert resp.status_code == 200
        assert resp.headers.get("x-request-id")

    async def test_request_id_available_inside_handler(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/ping")
        assert resp.json()["request_id"] == resp.headers["x-request-id"]

    async def test_reuses_client_supplied_request_id(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/ping", headers={"X-Request-ID": "client-rid-1"})
        assert resp.headers["x-request-id"] == "client-rid-1"
        assert resp.json()["request_id"] == "client-rid-1"

    async def test_rejects_malformed_client_request_id(
        self, client: AsyncClient
    ) -> None:
        bad = "x" * 500 + "\n injected"
        resp = await client.get("/ping", headers={"X-Request-ID": bad})
        assert resp.headers["x-request-id"] != bad
        assert re.fullmatch(r"[A-Za-z0-9._-]+", resp.headers["x-request-id"])

    async def test_request_id_cleared_after_request(
        self, client: AsyncClient
    ) -> None:
        await client.get("/ping")
        assert get_request_id() is None


class TestAccessLogMiddleware:
    async def test_emits_access_log_with_required_fields(
        self, client: AsyncClient
    ) -> None:
        with structlog.testing.capture_logs() as logs:
            await client.get("/ping")
        access = [e for e in logs if e["event"] == "http.access"]
        assert len(access) == 1
        entry = access[0]
        assert entry["method"] == "GET"
        assert entry["path"] == "/ping"
        assert entry["status_code"] == 200
        assert isinstance(entry["duration_ms"], (int, float))
        assert entry["log_level"] == "info"
