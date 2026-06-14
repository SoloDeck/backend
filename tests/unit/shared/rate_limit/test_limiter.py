"""Unit tests for the in-process fixed-window rate limiter."""

import pytest

from src.shared.exceptions.domain import RateLimitError
from src.shared.rate_limit import FixedWindowRateLimiter


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_requests_up_to_the_limit() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(max_requests=3, window_seconds=60, time_func=clock)

    # Three hits in the same window are all allowed.
    limiter.check("token-a")
    limiter.check("token-a")
    limiter.check("token-a")


def test_blocks_when_limit_exceeded_within_window() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(max_requests=2, window_seconds=60, time_func=clock)

    limiter.check("token-a")
    limiter.check("token-a")
    with pytest.raises(RateLimitError):
        limiter.check("token-a")


def test_window_resets_after_it_elapses() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(max_requests=1, window_seconds=60, time_func=clock)

    limiter.check("token-a")
    with pytest.raises(RateLimitError):
        limiter.check("token-a")

    clock.advance(61)  # past the window — old hit pruned
    limiter.check("token-a")


def test_keys_are_independent() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(max_requests=1, window_seconds=60, time_func=clock)

    limiter.check("token-a")
    # A different key has its own budget.
    limiter.check("token-b")


def test_reset_clears_a_single_key() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(max_requests=1, window_seconds=60, time_func=clock)

    limiter.check("token-a")
    limiter.reset("token-a")
    limiter.check("token-a")  # budget restored after reset


def test_invalid_configuration_rejected() -> None:
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(max_requests=0, window_seconds=60)
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(max_requests=1, window_seconds=0)
