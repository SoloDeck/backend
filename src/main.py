"""SoloDesk API — application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from src.ai.followup_generator.api.router import router as followup_router
from src.ai.lead_qualifier.api.router import router as lead_qualifier_router
from src.config.settings import settings
from src.infrastructure.database.session import engine
from src.infrastructure.redis.client import close_redis_pool, get_redis
from src.infrastructure.storage.object_storage import object_storage
from src.integrations.zalo.client import unusable_redirect_reason
from src.modules.admin.api.router import router as admin_router
from src.modules.ai_jobs.api.router import router as ai_jobs_router
from src.modules.analytics.api.router import router as analytics_router

# Module routers
from src.modules.auth.api.router import router as auth_router
from src.modules.clients.api.router import router as clients_router
from src.modules.contracts.api.public_router import router as public_contracts_router
from src.modules.contracts.api.router import router as contracts_router
from src.modules.deals.api.public_router import router as public_intake_router
from src.modules.deals.api.router import router as deals_router
from src.modules.freelancers.api.router import router as freelancers_router
from src.modules.intake_form.api.public_router import router as public_intake_form_router
from src.modules.intake_form.api.router import router as intake_form_router
from src.modules.invoices.api.public_router import router as public_invoices_router
from src.modules.invoices.api.router import router as invoices_router
from src.modules.notifications.api.router import router as notifications_router
from src.modules.payments.api.public_router import router as public_payments_router
from src.modules.payments.api.router import router as payments_router
from src.modules.projects.api.router import router as projects_router
from src.modules.proposals.api.public_router import router as public_proposals_router
from src.modules.proposals.api.router import router as proposals_router
from src.modules.reminders.api.router import router as reminders_router
from src.modules.subscriptions.api.router import router as subscriptions_router
from src.modules.tasks.api.router import router as tasks_router
from src.modules.users.api.router import router as users_router
from src.modules.zalo.api.router import router as zalo_router
from src.shared.exceptions.http import setup_exception_handlers
from src.shared.logging import (
    AccessLogMiddleware,
    RequestContextMiddleware,
    setup_logging,
)

setup_logging()
log = structlog.get_logger()

# Cap each readiness probe so a hung dependency can't hold the healthcheck open
# past the container healthcheck's own timeout.
_READINESS_TIMEOUT_SECONDS = 3.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("solodesk.startup", environment=settings.app_env)

    # Thiếu kho file thì HỎNG THẬT, nhưng hỏng lặng lẽ — phải kêu to.
    #
    # Staging từng chạy nhiều tuần với STORAGE_ENDPOINT rỗng: `ensure_bucket()` chỉ log
    # `warning` "storage.disabled", `/health/ready` không hề chạm tới kho file nên deploy
    # vẫn báo healthy, còn người dùng thì upload cái nào 409 cái đó. Hệ quả kéo theo:
    # deal không có file → AI chấm điểm không có gì để đọc → deal nào cũng 0/100 COLD.
    #
    # Ở môi trường deploy, thiếu cấu hình này là LỖI CẤU HÌNH, không phải chuyện bình
    # thường — log mức `error` để nó nổi lên trong log container ngay dòng đầu.  #Huynh
    deployed = settings.app_env not in ("development", "test")

    if not object_storage.enabled and deployed:
        log.error(
            "storage.disabled_in_deployed_env",
            app_env=settings.app_env,
            hint=(
                "Thiếu STORAGE_ENDPOINT/STORAGE_ACCESS_KEY. Mọi lần đính kèm file vào "
                "deal sẽ trả 409, và AI chấm điểm deal sẽ không đọc được file khách gửi."
            ),
        )

    # Zalo bật `real` mà thiếu config thì hỏng theo kiểu KHÓ LẦN NHẤT.
    #
    # `env_ignore_empty` (thêm ở PR #89) khiến biến rỗng rơi về mặc định, nên
    # `ZALO_OAUTH_REDIRECT_URI=` không đặt sẽ lặng lẽ thành `""`. Lúc đó
    # `get_zalo_client` vẫn dựng `RealZaloOAClient` bình thường, URL cấp quyền sinh ra
    # thiếu hẳn `redirect_uri`, và Zalo trả `-14003 Invalid redirect uri`. Triệu chứng
    # nằm ở PHÍA ZALO nên rất dễ đi lần nhầm sang phần khai báo domain — hôm 24/07 đã
    # mất cả buổi vì đúng kiểu này. Nêu thẳng biến nào thiếu ngay lúc khởi động.  #Huynh
    if deployed and settings.zalo_mode == "real":
        missing = [
            name
            for name, value in (
                ("ZALO_APP_ID", settings.zalo_app_id),
                ("ZALO_APP_SECRET", settings.zalo_app_secret),
            )
            if not value
        ]
        # Redirect URI kiểm bằng chính hàm mà `build_connect_url` dùng — một nguồn sự thật,
        # để log lúc khởi động và câu báo cho người dùng không bao giờ nói khác nhau.
        redirect_problem = unusable_redirect_reason(settings.zalo_oauth_redirect_uri)

        if missing or redirect_problem:
            log.error(
                "zalo.real_mode_misconfigured",
                app_env=settings.app_env,
                missing=missing,
                redirect_uri_problem=redirect_problem,
                hint=(
                    "ZALO_MODE=real nhưng cấu hình chưa dùng được. Kết nối Zalo OA sẽ hỏng "
                    "với lỗi -14003 Invalid redirect uri từ phía Zalo."
                ),
            )

    # `frontend_url` không chỉ dùng cho Zalo: nó dựng link trong THƯ GỬI KHÁCH (email báo
    # deal mới từ intake form, thư nhắc gói dịch vụ). Để nguyên mặc định `localhost` khi
    # deploy là gửi cho khách một đường dẫn chết mà không ai trong team thấy.  #Huynh
    if deployed and "localhost" in settings.frontend_url:
        log.error(
            "frontend_url_still_localhost",
            app_env=settings.app_env,
            frontend_url=settings.frontend_url,
            hint=(
                "Thiếu FRONTEND_URL. Link trong email gửi khách sẽ trỏ về localhost, "
                "và callback Zalo cũng đá người dùng về đó."
            ),
        )

    # Tạo bucket object storage nếu chưa có. Thiếu bước này thì upload file đầu tiên
    # nổ NoSuchBucket — MinIO không tự tạo bucket.  #Huynh
    try:
        object_storage.ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        # Không chặn app khởi động: mọi tính năng khác vẫn chạy được, chỉ upload file là
        # hỏng. Chặn ở đây là vì một file đính kèm mà cả hệ thống không lên.
        log.warning("storage.ensure_bucket_failed", error=str(exc))

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


# Origins only — NO `/api/v1` suffix. The generated paths already carry the full
# prefix (routers are mounted at `/api/v1/...`), so a server URL ending in `/api/v1`
# would make Swagger post to `/api/v1/api/v1/...`. The old hand-written contract had
# bare paths, which is why its server URLs did include the prefix.
_OPENAPI_SERVERS: list[dict[str, str]] = [
    {"url": "http://localhost:8000", "description": "Local development"},
    {"url": "https://api-staging.solodesk.space", "description": "Staging"},
    {"url": "https://api.solodesk.space", "description": "Production"},
]


def custom_openapi() -> dict[str, Any]:
    """Build the OpenAPI document from the routes actually registered on the app.

    This used to serve `contracts/openapi.yaml` — a hand-maintained document from the
    contract-first bootstrap, back when the routers were still scaffolding. The code
    outgrew it: 35 implemented endpoints had accumulated that the file never gained,
    among them `PATCH /proposals/{id}/price`, `POST /proposals/ai-generate`, every
    `/notifications` route and the whole reminder rules/preview/send group. Because
    Swagger renders this document, those endpoints were invisible at `/docs` and
    could not be called from there at all — they looked unimplemented to anyone
    reading the docs page, including us.

    `contracts/openapi.yaml` is kept as a design artefact. It is no longer the served
    truth, so it can no longer drift away from the implementation unnoticed.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Swagger UI sends "Try it out" requests to servers[0]. Outside production, put
    # localhost first so the docs page drives the local instance, not the deployed API.
    servers = list(_OPENAPI_SERVERS)
    if settings.debug or settings.app_env == "development":
        servers.sort(key=lambda s: "localhost" not in s["url"])
    schema["servers"] = servers

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
app.include_router(public_proposals_router, prefix=f"{API_V1}/proposals/public", tags=["Public"])
app.include_router(proposals_router, prefix=f"{API_V1}/proposals", tags=["Proposals"])
app.include_router(public_contracts_router, prefix=f"{API_V1}/contracts/public", tags=["Public"])
app.include_router(contracts_router, prefix=f"{API_V1}/contracts", tags=["Contracts"])
app.include_router(public_invoices_router, prefix=f"{API_V1}/invoices/public", tags=["Public"])
app.include_router(invoices_router, prefix=f"{API_V1}/invoices", tags=["Invoices"])
app.include_router(public_payments_router, prefix=f"{API_V1}/payments/webhooks", tags=["Public"])
app.include_router(payments_router, prefix=f"{API_V1}/payments", tags=["Payments"])
app.include_router(reminders_router, prefix=f"{API_V1}/reminders", tags=["Reminders"])
app.include_router(notifications_router, prefix=f"{API_V1}/notifications", tags=["Notifications"])
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
app.include_router(zalo_router, prefix=f"{API_V1}/zalo", tags=["Zalo"])
app.include_router(lead_qualifier_router, prefix=f"{API_V1}/ai")
app.include_router(followup_router, prefix=f"{API_V1}/ai")
app.include_router(ai_jobs_router, prefix=f"{API_V1}/ai/jobs", tags=["AI Jobs"])


# ---------------------------------------------------------------------------
# Xác thực quyền sở hữu domain/URL với Zalo: Zalo tải https://<domain>/zalo_verifier<TOKEN>.html
# rồi kiểm thẻ meta chứa <TOKEN>. Nội dung là mẫu CỐ ĐỊNH của Zalo (chỉ token đổi) → tự dựng
# từ tên file, phục vụ được MỌI token (Tiền tố URL / Domain / verify lại) mà không cần cấu
# hình từng cái. Pattern cụ thể (không catch-all) nên không che route khác; token chỉ nhận
# chữ-số để chặn XSS phản chiếu.  #Huynh
# ---------------------------------------------------------------------------
@app.get("/zalo_verifier{token}.html", include_in_schema=False)
async def zalo_domain_verify(token: str) -> HTMLResponse:
    if not token.isalnum():
        raise HTTPException(status_code=404)
    body = (
        '<!DOCTYPE html>\n<html lang="en">\n\n<head>\n'
        f'    <meta property="zalo-platform-site-verification" content="{token}" />\n'
        "</head>\n\n<body>\n"
        "There Is No Limit To What You Can Accomplish Using Zalo!\n"
        "</body>\n\n</html>\n"
    )
    return HTMLResponse(content=body)


# ---------------------------------------------------------------------------
# Root — trả 200 để các bộ kiểm tra domain (Zalo…) thấy site "sống", không phải 404.
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "SoloDesk API", "status": "ok", "docs": "/docs"}


# ---------------------------------------------------------------------------
# API v1 root — Swagger UI probes this on load
# ---------------------------------------------------------------------------
@app.get(f"{API_V1}", include_in_schema=False)
async def api_v1_root() -> dict[str, str]:
    return {"message": "SoloDesk API v1", "docs": "/docs"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"], include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Liveness — the process is up. Deliberately touches no dependency."""
    return {"status": "ok", "environment": settings.app_env}


async def _probe_database() -> None:
    async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


async def _probe_redis() -> None:
    async with asyncio.timeout(_READINESS_TIMEOUT_SECONDS):
        redis = await get_redis()
        await redis.ping()


@app.get("/health/ready", tags=["Health"], include_in_schema=False)
async def readiness_check() -> JSONResponse:
    """Readiness — every dependency the API needs to serve a real request.

    The container healthcheck probes this, not ``/health``: a liveness-only
    probe reports "healthy" while Postgres is unreachable and every business
    endpoint returns 500, which is exactly how a broken deploy stays invisible.
    """
    # Probed concurrently, not in sequence: two dependencies hanging one after
    # the other would push the response past the container healthcheck's own
    # timeout, turning a clean 503 into an aborted request. Concurrent probes
    # keep the worst case at _READINESS_TIMEOUT_SECONDS regardless of how many
    # dependencies are added here later.
    names = ("database", "redis")
    results = await asyncio.gather(_probe_database(), _probe_redis(), return_exceptions=True)

    checks: dict[str, str] = {}
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            checks[name] = f"fail: {type(result).__name__}"
            log.warning("health.dependency_unavailable", dependency=name, error=str(result)[:200])
        else:
            checks[name] = "ok"

    ready = all(status == "ok" for status in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "environment": settings.app_env,
            "checks": checks,
        },
    )
