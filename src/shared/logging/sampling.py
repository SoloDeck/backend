"""In-memory log sampling to prevent log storms in production.

A fixed-window counter keyed by ``(level, event)``. Once more than
``max_per_window`` identical entries are seen within ``window_seconds``,
further occurrences raise :class:`structlog.DropEvent` so they never reach the
sink. ERROR/CRITICAL entries are always allowed through — we never sample away
failures.
"""

import time
from collections.abc import Callable
from typing import Any

import structlog

_ALWAYS_KEEP = frozenset({"error", "critical", "exception"})


class RateLimiterProcessor:
    def __init__(
        self,
        max_per_window: int = 100,
        window_seconds: float = 10.0,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._time = time_fn
        # key -> (window_start, count)
        self._buckets: dict[tuple[str, str], tuple[float, int]] = {}

    def __call__(
        self, _logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        if method_name.lower() in _ALWAYS_KEEP:
            return event_dict

        key = (method_name, str(event_dict.get("event", "")))
        now = self._time()
        start, count = self._buckets.get(key, (now, 0))

        if now - start >= self._window:
            start, count = now, 0

        count += 1
        self._buckets[key] = (start, count)

        if count > self._max:
            raise structlog.DropEvent
        return event_dict
