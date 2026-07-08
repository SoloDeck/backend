"""Maps domain exceptions raised inside an AI job's Celery task to a JobError.

Mirrors the code/status mapping in src/shared/exceptions/http.py, plus a
`retryable` verdict: True for failures a repeated attempt could plausibly
fix (rate limits, transient LLM errors), False for failures that will keep
happening until something about the request changes.
"""

from src.modules.ai_jobs.domain.value_objects.job_error import JobError
from src.shared.exceptions.domain import (
    AIGenerationError,
    AlreadyExistsError,
    AuthenticationError,
    BusinessRuleError,
    DomainError,
    EntitlementError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from src.shared.responses.error import ErrorCode

_NOT_RETRYABLE: tuple[tuple[type[DomainError], ErrorCode], ...] = (
    (NotFoundError, ErrorCode.NOT_FOUND),
    (AlreadyExistsError, ErrorCode.CONFLICT),
    (AuthenticationError, ErrorCode.UNAUTHORIZED),
    (ForbiddenError, ErrorCode.FORBIDDEN),
    (EntitlementError, ErrorCode.SUBSCRIPTION_REQUIRED),
    (ValidationError, ErrorCode.VALIDATION_FAILED),
    (BusinessRuleError, ErrorCode.BUSINESS_RULE_VIOLATION),
)

_RETRYABLE: tuple[tuple[type[DomainError], ErrorCode], ...] = (
    (RateLimitError, ErrorCode.RATE_LIMITED),
    (AIGenerationError, ErrorCode.AI_QUOTA_EXCEEDED),
)


def to_job_error(exc: Exception) -> JobError:
    for exc_type, code in _NOT_RETRYABLE:
        if isinstance(exc, exc_type):
            return JobError(code=code.value, message=str(exc), retryable=False)

    for exc_type, code in _RETRYABLE:
        if isinstance(exc, exc_type):
            return JobError(code=code.value, message=str(exc), retryable=True)

    if isinstance(exc, DomainError):
        return JobError(
            code=ErrorCode.BUSINESS_RULE_VIOLATION.value, message=str(exc), retryable=False
        )

    return JobError(
        code=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="An unexpected error occurred",
        retryable=False,
    )
