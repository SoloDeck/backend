"""HTTP middleware: request correlation id + structured access log.

``RequestContextMiddleware`` must wrap ``AccessLogMiddleware`` (add it *last*
so it is outermost) so the correlation id is bound before the access entry is
emitted.
"""

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.shared.logging.config import get_logger
from src.shared.logging.context import bind_request_id, clear_request_id, new_request_id

REQUEST_ID_HEADER = "X-Request-ID"
# Accept only safe, bounded ids from clients to avoid log injection / abuse.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

_log = get_logger("solodesk.access")


def _sanitize_request_id(raw: str | None) -> str:
    if raw and _VALID_REQUEST_ID.fullmatch(raw):
        return raw
    return new_request_id()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a correlation id for the request and echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        rid = bind_request_id(_sanitize_request_id(request.headers.get(REQUEST_ID_HEADER)))
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        # Clear only on the success path. If the handler raised, the exception
        # propagates to Starlette's ServerErrorMiddleware (outside this
        # middleware) where the global handler still needs the id to log it.
        # Each request rebinds the id on entry, so no stale id leaks.
        clear_request_id()
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one INFO access log per request, independent of handler logging."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _log.info(
            "http.access",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
