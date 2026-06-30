"""Request-scoped correlation id, propagated via :mod:`contextvars`.

The id is stored both in a dedicated ``ContextVar`` (for fast lookup) and in
structlog's contextvars store (so it is merged into every log entry emitted
during the request lifecycle, without threading it through call signatures).
"""

import uuid
from contextvars import ContextVar

import structlog

REQUEST_ID_KEY = "request_id"

_request_id_ctx: ContextVar[str | None] = ContextVar("solodesk_request_id", default=None)


def new_request_id() -> str:
    """Generate a fresh, hard-to-guess correlation id."""
    return uuid.uuid4().hex


def bind_request_id(request_id: str | None = None) -> str:
    """Bind ``request_id`` (or a new one) to the current context.

    Also binds it into structlog's contextvars so it appears in all log entries.
    Returns the id that was bound.
    """
    rid = request_id or new_request_id()
    _request_id_ctx.set(rid)
    structlog.contextvars.bind_contextvars(**{REQUEST_ID_KEY: rid})
    return rid


def get_request_id() -> str | None:
    """Return the correlation id bound to the current context, if any."""
    return _request_id_ctx.get()


def clear_request_id() -> None:
    """Remove the correlation id from the current context."""
    _request_id_ctx.set(None)
    structlog.contextvars.unbind_contextvars(REQUEST_ID_KEY)
