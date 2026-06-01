"""Translate domain exceptions and FastAPI errors to the standard response envelope."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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
from src.shared.responses.error import ErrorCode, ValidationErrorDetail
from src.shared.responses.response import ErrorResponse


def _err(http_code: int, error_code: str, message: str, details: list | None = None) -> JSONResponse:
    body = ErrorResponse.from_error(
        http_code=http_code,
        error_code=error_code,
        message=message,
        details=details,
    )
    return JSONResponse(status_code=http_code, content=body.model_dump())


def setup_exception_handlers(app: FastAPI) -> None:

    # ------------------------------------------------------------------
    # FastAPI / Starlette built-ins
    # ------------------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"] if loc != "body")
            details.append(
                ValidationErrorDetail(field=field or "request", message=err["msg"])
            )
        return _err(422, ErrorCode.VALIDATION_FAILED, "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            400: ErrorCode.VALIDATION_FAILED,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            500: ErrorCode.INTERNAL_SERVER_ERROR,
        }
        error_code = code_map.get(exc.status_code, ErrorCode.INTERNAL_SERVER_ERROR)
        return _err(exc.status_code, error_code, str(exc.detail))

    # ------------------------------------------------------------------
    # Domain exceptions
    # ------------------------------------------------------------------

    @app.exception_handler(AuthenticationError)
    async def authentication(_: Request, exc: AuthenticationError) -> JSONResponse:
        return _err(401, ErrorCode.UNAUTHORIZED, exc.message)

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _err(404, ErrorCode.NOT_FOUND, exc.message)

    @app.exception_handler(AlreadyExistsError)
    async def already_exists(_: Request, exc: AlreadyExistsError) -> JSONResponse:
        return _err(409, ErrorCode.CONFLICT, exc.message)

    @app.exception_handler(ForbiddenError)
    async def forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return _err(403, ErrorCode.FORBIDDEN, exc.message)

    @app.exception_handler(EntitlementError)
    async def entitlement(_: Request, exc: EntitlementError) -> JSONResponse:
        return _err(402, ErrorCode.SUBSCRIPTION_REQUIRED, exc.message)

    @app.exception_handler(BusinessRuleError)
    async def business_rule(_: Request, exc: BusinessRuleError) -> JSONResponse:
        return _err(409, ErrorCode.BUSINESS_RULE_VIOLATION, exc.message)

    @app.exception_handler(AIGenerationError)
    async def ai_error(_: Request, exc: AIGenerationError) -> JSONResponse:
        return _err(502, ErrorCode.AI_QUOTA_EXCEEDED, exc.message)

    @app.exception_handler(DomainError)
    async def domain_fallback(_: Request, exc: DomainError) -> JSONResponse:
        return _err(400, ErrorCode.BUSINESS_RULE_VIOLATION, exc.message)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        return _err(500, ErrorCode.INTERNAL_SERVER_ERROR, "An unexpected error occurred")
