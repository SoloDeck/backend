"""Unit tests for the retry-decision helper in src.workers.ai_jobs.tasks.

The task bodies themselves (generate_proposal_async, generate_contract_async)
open a real DB engine internally and are exercised via integration tests /
manual runs, not mocked in isolation here — matching how qualify_deal_async_by_id
is treated elsewhere in this codebase (only its `.delay()` call sites are mocked).
"""

from unittest.mock import AsyncMock, MagicMock

from src.shared.exceptions.domain import NotFoundError, RateLimitError
from src.workers.ai_jobs.tasks import _should_retry, _was_cancelled


class TestShouldRetry:
    def test_retryable_error_with_attempts_remaining_retries(self) -> None:
        assert _should_retry(RateLimitError("slow down"), current_retries=0, max_retries=3) is True

    def test_retryable_error_at_last_attempt_does_not_retry(self) -> None:
        assert (
            _should_retry(RateLimitError("slow down"), current_retries=3, max_retries=3) is False
        )

    def test_non_retryable_error_never_retries(self) -> None:
        assert (
            _should_retry(NotFoundError("gone"), current_retries=0, max_retries=3) is False
        )


class TestWasCancelled:
    async def test_returns_true_when_job_now_cancelled(self) -> None:
        job = MagicMock(status="cancelled")
        jobs_repo = AsyncMock()
        jobs_repo.refresh = AsyncMock()

        assert await _was_cancelled(jobs_repo, job) is True
        jobs_repo.refresh.assert_awaited_once_with(job)

    async def test_returns_false_when_job_still_running(self) -> None:
        job = MagicMock(status="running")
        jobs_repo = AsyncMock()
        jobs_repo.refresh = AsyncMock()

        assert await _was_cancelled(jobs_repo, job) is False
