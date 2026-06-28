"""SoloDesk structured logging package.

Public API:
    setup_logging()  — configure once at startup (call before app init).
    get_logger(name) — obtain a structlog logger anywhere.
"""

from src.shared.logging.config import get_logger, setup_logging
from src.shared.logging.context import (
    bind_request_id,
    clear_request_id,
    get_request_id,
)
from src.shared.logging.middleware import (
    AccessLogMiddleware,
    RequestContextMiddleware,
)

__all__ = [
    "setup_logging",
    "get_logger",
    "bind_request_id",
    "clear_request_id",
    "get_request_id",
    "AccessLogMiddleware",
    "RequestContextMiddleware",
]
