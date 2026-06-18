"""In-process fixed-window rate limiter.

A deliberately small, dependency-free guard for public (unauthenticated)
endpoints. It tracks recent hit timestamps per key inside the worker process.

Scope and caveats:
- Per-process only. Behind multiple workers/replicas each process keeps its own
  window, so the effective limit is `max_requests * num_processes`. For a hard,
  cluster-wide cap, layer a gateway/Redis limit on top — this class is the
  "rate-limit cơ bản" (basic) application-layer guard, not the last line.
- The clock is injectable (`time_func`) so the window logic is unit-testable
  without sleeping.
"""

import threading
import time
from collections.abc import Callable

from src.shared.exceptions.domain import RateLimitError


class FixedWindowRateLimiter:
    """Allow at most `max_requests` per `window_seconds` for each key."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max = max_requests
        self._window = window_seconds
        self._time = time_func
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record a hit for `key`; raise RateLimitError if the window is full.

        Expired timestamps are pruned on each call so memory for an idle key is
        reclaimed the next time it is touched.
        """
        now = self._time()
        cutoff = now - self._window
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(recent) >= self._max:
                self._hits[key] = recent
                raise RateLimitError(
                    "Too many submissions from this link. Please try again later."
                )
            recent.append(now)
            self._hits[key] = recent

    def reset(self, key: str | None = None) -> None:
        """Clear tracked hits for one key, or all keys when `key` is None."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
