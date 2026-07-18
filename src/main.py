"""SoloDesk API — application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.ai.lead_qualifier.api.router import router as lead_qualifier_router
from src.config.settings import settings
from src.infrastructure.database.session import engine
from src.infrastructure.redis.client import close_redis_pool
from src.modules.admin.api.router import router as admin_router
from src.modules.ai_jobs.api.router import router as ai_jobs_router
from src.modules.analytics.api.router import router as analytics_router

# Module routers
from src.modules.auth.api.router import router as auth_router
from src.modules.clients.api.router import router as clients_router
from src.modules.contracts.api.router import router as contracts_router
from src.modules.deals.api.public_router import router as public_intake_router
from src.modules.deals.api.router import router as deals_router
from src.modules.freelancers.api.router import router as freelancers_router
from src.modules.intake_form.api.public_router import router as public_intake_form_router
from src.modules.intake_form.api.router import router as intake_form_router
from src.modules.invoices.api.public_router import router as public_invoices_router
from src.modules.invoices.api.router import router as invoices_router
from src.modules.payments.api.public_router import router as public_payments_router
from src.modules.payments.api.router import router as payments_router
from src.modules.projects.api.router import router as projects_router
from src.modules.proposals.api.router import router as proposals_router
from src.modules.reminders.api.router import router as reminders_router
from src.modules.subscriptions.api.router import router as subscriptions_router
from src.modules.tasks.api.router import router as tasks_router
from src.modules.users.api.router import router as users_router
from src.shared.exceptions.http import setup_exception_handlers
from src.shared.logging import (
    AccessLogMiddleware,
    RequestContextMiddleware,
    setup_logging,
)

setup_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("solodesk.startup", environment=settings.app_env)
    yield
    await engine.dispose()
    await close_redis_pool()
    log.info("solodesk.shutdown")


app = FastAPI(
    title="SoloDesk API",
    version="1.0.0",
    description="AI-powered CRM for Vietnamese freelancers",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    swagger_ui_parameters={"tryItOutEnabled": True},  # Luôn bật sẵn chế độ nhập và chạy API
)


def custom_openapi() -> dict:
    """Serve the contract-first OpenAPI document while API routers are scaffolded."""
    if app.openapi_schema:
        return app.openapi_schema

    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "openapi.yaml"
    with contract_path.open(encoding="utf-8") as spec_file:
        schema = yaml.safe_load(spec_file)

    # In development, promote the localhost server to the top so Swagger UI
    # sends requests to the local instance instead of production.
    if settings.debug or settings.app_env == "development":
        servers: list[dict] = schema.get("servers", [])
        local = [s for s in servers if "localhost" in s.get("url", "")]
        others = [s for s in servers if "localhost" not in s.get("url", "")]
        if local:
            schema["servers"] = local + others

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# Order matters: middleware added last is outermost. RequestContextMiddleware
# must be outermost so the correlation id is bound before access logging and
# request handling run.
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
setup_exception_handlers(app)

# ---------------------------------------------------------------------------
# Routers — API v1
# ---------------------------------------------------------------------------
API_V1 = "/api/v1"

app.include_router(auth_router, prefix=f"{API_V1}/auth", tags=["Auth"])
app.include_router(users_router, prefix=f"{API_V1}/users", tags=["Users"])
app.include_router(subscriptions_router, prefix=f"{API_V1}/subscriptions", tags=["Subscriptions"])
app.include_router(clients_router, prefix=f"{API_V1}/clients", tags=["Clients"])
app.include_router(deals_router, prefix=f"{API_V1}/deals", tags=["Deals"])
app.include_router(proposals_router, prefix=f"{API_V1}/proposals", tags=["Proposals"])
app.include_router(contracts_router, prefix=f"{API_V1}/contracts", tags=["Contracts"])
app.include_router(public_invoices_router, prefix=f"{API_V1}/invoices/public", tags=["Public"])
app.include_router(invoices_router, prefix=f"{API_V1}/invoices", tags=["Invoices"])
app.include_router(
    public_payments_router, prefix=f"{API_V1}/payments/webhooks", tags=["Public"]
)
app.include_router(payments_router, prefix=f"{API_V1}/payments", tags=["Payments"])
app.include_router(reminders_router, prefix=f"{API_V1}/reminders", tags=["Reminders"])
app.include_router(projects_router, prefix=f"{API_V1}/projects", tags=["Projects"])
# Tasks use polymorphic paths (/projects/.../tasks, /deals/.../tasks,
# /reminders/.../tasks, /tasks/...) so the router carries full paths under API_V1.
app.include_router(tasks_router, prefix=API_V1, tags=["Tasks"])
app.include_router(analytics_router, prefix=f"{API_V1}/analytics", tags=["Analytics"])
app.include_router(public_intake_form_router, prefix=f"{API_V1}/intake", tags=["Public"])
app.include_router(public_intake_router, prefix=f"{API_V1}/intake", tags=["Public"])
app.include_router(intake_form_router, prefix=f"{API_V1}/intake-form", tags=["Intake Form"])
app.include_router(freelancers_router, prefix=f"{API_V1}/public/freelancers", tags=["Public"])
app.include_router(projects_router, prefix=f"{API_V1}/projects", tags=["Projects"])
app.include_router(admin_router, prefix=f"{API_V1}/admin", tags=["Admin"])
app.include_router(lead_qualifier_router, prefix=f"{API_V1}/ai")
app.include_router(ai_jobs_router, prefix=f"{API_V1}/ai/jobs", tags=["AI Jobs"])


# ---------------------------------------------------------------------------
# API v1 root — Swagger UI probes this on load
# ---------------------------------------------------------------------------
@app.get(f"{API_V1}", include_in_schema=False)
async def api_v1_root() -> dict:
    return {"message": "SoloDesk API v1", "docs": "/docs"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"], include_in_schema=False)
async def health_check() -> dict:
    return {"status": "ok", "environment": settings.app_env}
