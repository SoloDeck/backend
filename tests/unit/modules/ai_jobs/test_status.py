"""Unit tests for src.modules.ai_jobs.domain.value_objects.status."""

from src.modules.ai_jobs.domain.value_objects.status import (
    TERMINAL_STATUSES,
    AiJobStatus,
    can_transition,
)


class TestCanTransition:
    def test_queued_to_running_allowed(self) -> None:
        assert can_transition(AiJobStatus.QUEUED, AiJobStatus.RUNNING) is True

    def test_queued_to_cancelled_allowed(self) -> None:
        assert can_transition(AiJobStatus.QUEUED, AiJobStatus.CANCELLED) is True

    def test_running_to_succeeded_allowed(self) -> None:
        assert can_transition(AiJobStatus.RUNNING, AiJobStatus.SUCCEEDED) is True

    def test_running_to_failed_allowed(self) -> None:
        assert can_transition(AiJobStatus.RUNNING, AiJobStatus.FAILED) is True

    def test_running_to_cancelled_allowed(self) -> None:
        assert can_transition(AiJobStatus.RUNNING, AiJobStatus.CANCELLED) is True

    def test_queued_to_succeeded_not_allowed(self) -> None:
        assert can_transition(AiJobStatus.QUEUED, AiJobStatus.SUCCEEDED) is False

    def test_terminal_statuses_have_no_outgoing_transitions(self) -> None:
        for status in TERMINAL_STATUSES:
            for target in AiJobStatus:
                assert can_transition(status, target) is False

    def test_terminal_statuses_set(self) -> None:
        expected = {AiJobStatus.SUCCEEDED, AiJobStatus.FAILED, AiJobStatus.CANCELLED}
        assert expected == TERMINAL_STATUSES
