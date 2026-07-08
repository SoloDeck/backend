"""Unit tests for src.modules.ai_jobs.application.errors.to_job_error."""

from src.modules.ai_jobs.application.errors import to_job_error
from src.shared.exceptions.domain import (
    AIGenerationError,
    AIOutputParseError,
    AlreadyExistsError,
    AuthenticationError,
    BusinessRuleError,
    EntitlementError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from src.shared.responses.error import ErrorCode


class TestToJobError:
    def test_not_found_is_not_retryable(self) -> None:
        error = to_job_error(NotFoundError("Deal not found"))
        assert error.code == ErrorCode.NOT_FOUND.value
        assert error.message == "Deal not found"
        assert error.retryable is False

    def test_already_exists_maps_to_conflict(self) -> None:
        error = to_job_error(AlreadyExistsError("dup"))
        assert error.code == ErrorCode.CONFLICT.value
        assert error.retryable is False

    def test_authentication_error_maps_to_unauthorized(self) -> None:
        error = to_job_error(AuthenticationError("bad creds"))
        assert error.code == ErrorCode.UNAUTHORIZED.value
        assert error.retryable is False

    def test_forbidden_error_maps_to_forbidden(self) -> None:
        error = to_job_error(ForbiddenError("nope"))
        assert error.code == ErrorCode.FORBIDDEN.value
        assert error.retryable is False

    def test_entitlement_error_is_not_retryable(self) -> None:
        error = to_job_error(EntitlementError("upgrade needed", entitlement="can_use_ai"))
        assert error.code == ErrorCode.SUBSCRIPTION_REQUIRED.value
        assert error.retryable is False

    def test_validation_error_is_not_retryable(self) -> None:
        error = to_job_error(ValidationError("bad payload"))
        assert error.code == ErrorCode.VALIDATION_FAILED.value
        assert error.retryable is False

    def test_business_rule_error_is_not_retryable(self) -> None:
        error = to_job_error(BusinessRuleError("nope"))
        assert error.code == ErrorCode.BUSINESS_RULE_VIOLATION.value
        assert error.retryable is False

    def test_invalid_state_transition_is_a_business_rule_error(self) -> None:
        error = to_job_error(InvalidStateTransitionError("deal", "lost", "active"))
        assert error.code == ErrorCode.BUSINESS_RULE_VIOLATION.value
        assert error.retryable is False

    def test_rate_limit_error_is_retryable(self) -> None:
        error = to_job_error(RateLimitError("slow down"))
        assert error.code == ErrorCode.RATE_LIMITED.value
        assert error.retryable is True

    def test_ai_generation_error_is_retryable(self) -> None:
        error = to_job_error(AIGenerationError("timeout"))
        assert error.code == ErrorCode.AI_QUOTA_EXCEEDED.value
        assert error.retryable is True

    def test_ai_output_parse_error_is_retryable(self) -> None:
        error = to_job_error(AIOutputParseError("bad json", raw_output="{"))
        assert error.code == ErrorCode.AI_QUOTA_EXCEEDED.value
        assert error.retryable is True

    def test_unknown_exception_falls_back_to_internal_error(self) -> None:
        error = to_job_error(ValueError("boom"))
        assert error.code == ErrorCode.INTERNAL_SERVER_ERROR.value
        assert error.retryable is False
        # Raw message is never leaked for unmapped exceptions.
        assert error.message == "An unexpected error occurred"
