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


class TestProviderErrors:
    """Lỗi do nhà cung cấp mô hình trả về, nhận biết qua `status_code` / `code`.

    Có thật: Groq trả 413 "TPM Limit 8000, Requested 8462" thì màn hình lại hiện "Bạn cần
    nâng cấp gói để dùng AI" — vì mọi lỗi lạ đều thành INTERNAL_SERVER_ERROR + retryable
    False, và giao diện dịch retryable False thành "phải nâng gói".
    """

    def test_groq_token_limit_keeps_the_real_reason(self) -> None:
        class GroqAPIError(Exception):
            status_code = 413

        error = to_job_error(
            GroqAPIError(
                "Error code: 413 - Request too large ... tokens per minute (TPM): "
                "Limit 8000, Requested 8462"
            )
        )
        assert error.code == ErrorCode.AI_PROVIDER_ERROR.value
        # Chờ một lát là hết — đừng khuyên người dùng đi nâng gói.
        assert error.retryable is True
        assert "hạn mức token" in error.message
        # Nguyên văn của nhà cung cấp phải còn lại: đây là thứ duy nhất chỉ đúng thủ phạm.
        assert "Requested 8462" in error.message

    def test_genai_style_code_attribute_is_recognised(self) -> None:
        """google-genai gắn mã HTTP vào `code` chứ không phải `status_code`."""

        class GenaiAPIError(Exception):
            code = 429

        error = to_job_error(GenaiAPIError("resource exhausted"))
        assert error.code == ErrorCode.AI_PROVIDER_ERROR.value
        assert error.retryable is True

    def test_bad_api_key_is_not_retryable(self) -> None:
        class GroqAPIError(Exception):
            status_code = 401

        error = to_job_error(GroqAPIError("invalid api key"))
        assert error.code == ErrorCode.AI_PROVIDER_ERROR.value
        # Sai khoá thì gọi lại bao nhiêu lần cũng thế.
        assert error.retryable is False

    def test_long_provider_detail_is_truncated(self) -> None:
        class GroqAPIError(Exception):
            status_code = 500

        error = to_job_error(GroqAPIError("x" * 5000))
        assert error.code == ErrorCode.AI_PROVIDER_ERROR.value
        assert len(error.message) < 500

    def test_non_http_attribute_is_ignored(self) -> None:
        """`code` kiểu chuỗi (vd errno tên) không phải mã HTTP — đừng nhận nhầm."""

        class SocketError(Exception):
            code = "ECONNRESET"

        error = to_job_error(SocketError("boom"))
        assert error.code == ErrorCode.INTERNAL_SERVER_ERROR.value
