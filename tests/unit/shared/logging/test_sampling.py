"""Tests for the production log-sampling (rate-limit) processor."""

import pytest
import structlog

from src.shared.logging.sampling import RateLimiterProcessor


class TestRateLimiterProcessor:
    def test_allows_events_under_threshold(self) -> None:
        proc = RateLimiterProcessor(max_per_window=3, window_seconds=60)
        for _ in range(3):
            assert proc(None, "info", {"event": "tick"}) == {"event": "tick"}

    def test_drops_repeated_events_over_threshold(self) -> None:
        proc = RateLimiterProcessor(max_per_window=2, window_seconds=60)
        proc(None, "info", {"event": "spam"})
        proc(None, "info", {"event": "spam"})
        with pytest.raises(structlog.DropEvent):
            proc(None, "info", {"event": "spam"})

    def test_distinct_events_counted_separately(self) -> None:
        proc = RateLimiterProcessor(max_per_window=1, window_seconds=60)
        assert proc(None, "info", {"event": "a"}) == {"event": "a"}
        assert proc(None, "info", {"event": "b"}) == {"event": "b"}

    def test_window_resets_after_expiry(self) -> None:
        clock = {"t": 1000.0}
        proc = RateLimiterProcessor(max_per_window=1, window_seconds=10, time_fn=lambda: clock["t"])
        assert proc(None, "info", {"event": "x"}) == {"event": "x"}
        with pytest.raises(structlog.DropEvent):
            proc(None, "info", {"event": "x"})
        clock["t"] += 11
        assert proc(None, "info", {"event": "x"}) == {"event": "x"}

    def test_errors_are_never_dropped(self) -> None:
        proc = RateLimiterProcessor(max_per_window=1, window_seconds=60)
        proc(None, "error", {"event": "boom"})
        # second error of same key must still pass through
        assert proc(None, "error", {"event": "boom"}) == {"event": "boom"}
