"""Structured logging setup — one codebase, three environments.

* development → human-friendly colored console, DEBUG default.
* staging     → JSON to stdout, INFO default (production-like).
* production  → JSON to stdout, INFO default, sampling enabled, never DEBUG.

Output goes to stdout only (12-factor). Log collection is the deploy
environment's job. stdout I/O is offloaded to a background thread via
``QueueHandler`` + ``QueueListener`` so logging never blocks the event loop.
"""

import atexit
import logging
import logging.handlers
import queue
import sys
from typing import Any, Literal

import structlog

from src.config.settings import settings
from src.shared.logging.redaction import redact_processor
from src.shared.logging.sampling import RateLimiterProcessor

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_DEFAULT_LEVEL = {"development": "DEBUG", "staging": "INFO", "production": "INFO"}

_listener: logging.handlers.QueueListener | None = None


# ---------------------------------------------------------------------------
# Pure resolution helpers (unit-tested in isolation)
# ---------------------------------------------------------------------------
def resolve_log_level(app_env: str, override: str | None) -> int:
    """Resolve the effective numeric log level for an environment.

    ``override`` (the ``LOG_LEVEL`` env var) wins when valid. Production is
    clamped to INFO minimum — DEBUG is never emitted in production.
    """
    name = (override or "").strip().upper()
    if name not in _VALID_LEVELS:
        name = _DEFAULT_LEVEL.get(app_env, "INFO")
    level = logging.getLevelName(name)
    if app_env == "production" and level < logging.INFO:
        level = logging.INFO
    return level


def resolve_log_format(app_env: str, override: str | None) -> Literal["console", "json"]:
    """Resolve the effective renderer. ``override`` (``LOG_FORMAT``) wins."""
    fmt = (override or "").strip().lower()
    if fmt in ("console", "json"):
        return fmt  # type: ignore[return-value]
    return "console" if app_env == "development" else "json"


def resolve_log_request_body(app_env: str, flag: bool) -> bool:
    """Request-body logging is a debug aid — never allowed in production."""
    return False if app_env == "production" else bool(flag)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def _static_fields(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["service"] = settings.service_name
    event_dict["environment"] = settings.app_env
    return event_dict


def _build_processors(fmt: str, app_env: str) -> list[structlog.types.Processor]:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _static_fields,
        structlog.processors.StackInfoRenderer(),
        redact_processor,
    ]
    if fmt == "json":
        json_chain: list[structlog.types.Processor] = list(shared)
        if app_env == "production":
            json_chain.append(RateLimiterProcessor())
        json_chain += [
            structlog.processors.dict_tracebacks,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ]
        return json_chain
    return [*shared, structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())]


def _install_queue_handler(level: int) -> None:
    """Route the root logger through a non-blocking queue → stdout."""
    global _listener
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    if _listener is not None:
        _listener.stop()

    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(message)s"))
    _listener = logging.handlers.QueueListener(
        log_queue, stream, respect_handler_level=True
    )
    _listener.start()
    atexit.register(_listener.stop)
    root.addHandler(logging.handlers.QueueHandler(log_queue))


def setup_logging() -> None:
    """Configure structlog + stdlib logging. Call once at startup."""
    level = resolve_log_level(settings.app_env, settings.log_level)
    fmt = resolve_log_format(settings.app_env, settings.log_format)

    _install_queue_handler(level)

    structlog.configure(
        processors=_build_processors(fmt, settings.app_env),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger. Preferred entry point for all modules."""
    return structlog.get_logger(name)
