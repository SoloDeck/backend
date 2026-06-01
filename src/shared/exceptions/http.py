"""Translate domain exceptions to FastAPI HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.shared.exceptions.domain import (
    AIGenerationError,
    AlreadyExistsError,
    AuthenticationError,
    BusinessRuleError,
    DomainError,
    EntitlementError,
    ForbiddenError,
    NotFoundError,
)


def _error(code: str, message: str, **extra: object) -> dict:  # type: ignore[misc]
    body: dict = {"error": code, "message": message}  # type: ignore[type-arg]
    body.update(extra)
    return body


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthenticationError)
    async def authentication(_: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content=_error("UNAUTHORIZED", exc.message))

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error("NOT_FOUND", exc.message))

    @app.exception_handler(AlreadyExistsError)
    async def already_exists(_: Request, exc: AlreadyExistsError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error("CONFLICT", exc.message))

    @app.exception_handler(ForbiddenError)
    async def forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content=_error("FORBIDDEN", exc.message))

    @app.exception_handler(EntitlementError)
    async def entitlement(_: Request, exc: EntitlementError) -> JSONResponse:
        return JSONResponse(
            status_code=402,
            content=_error(
                "ENTITLEMENT_REQUIRED",
                exc.message,
                entitlement=exc.entitlement,
                upgrade_url="/api/v1/subscriptions/plans",
            ),
        )

    @app.exception_handler(BusinessRuleError)
    async def business_rule(_: Request, exc: BusinessRuleError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error("CONFLICT", exc.message))

    @app.exception_handler(AIGenerationError)
    async def ai_error(_: Request, exc: AIGenerationError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content=_error("AI_GENERATION_FAILED", exc.message)
        )

    @app.exception_handler(DomainError)
    async def domain_fallback(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content=_error("DOMAIN_ERROR", exc.message)
        )
