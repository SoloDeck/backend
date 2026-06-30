"""The global exception handler must log full context before returning 500."""

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.shared.exceptions.http import setup_exception_handlers
from src.shared.logging.middleware import RequestContextMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    setup_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> dict:
        raise ValueError("kaboom secret leak")

    return app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestUnhandledExceptionLogging:
    async def test_returns_generic_500_without_leaking_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/boom")
        assert resp.status_code == 500
        body = resp.text
        assert "kaboom" not in body  # stack/detail must not leak to client

    async def test_logs_error_with_request_context(self, client: AsyncClient) -> None:
        with structlog.testing.capture_logs() as logs:
            await client.get("/boom")
        errors = [e for e in logs if e["event"] == "http.unhandled_exception"]
        assert len(errors) == 1
        entry = errors[0]
        assert entry["log_level"] == "error"
        assert entry["method"] == "GET"
        assert entry["path"] == "/boom"
        assert entry["request_id"]
        # The exception is passed for exc_info so the sink renders its traceback.
        assert isinstance(entry["exc_info"], ValueError)
