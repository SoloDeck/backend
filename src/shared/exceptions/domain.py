"""Domain exception hierarchy.

All business rule violations raise subclasses of DomainError.
HTTP translation happens in src/shared/exceptions/http.py.
"""


class DomainError(Exception):
    """Base for all domain-layer exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Resource errors
# ---------------------------------------------------------------------------


class NotFoundError(DomainError):
    """Requested resource does not exist or is not accessible by this user."""


class AlreadyExistsError(DomainError):
    """Uniqueness constraint violated (e.g. duplicate client email)."""


# ---------------------------------------------------------------------------
# Authorization errors
# ---------------------------------------------------------------------------


class AuthenticationError(DomainError):
    """Invalid credentials or unauthenticated request."""


class ForbiddenError(DomainError):
    """Authenticated user is not permitted to perform this action."""


class EntitlementError(DomainError):
    """Subscription plan does not include the requested feature."""

    def __init__(self, message: str, entitlement: str) -> None:
        super().__init__(message)
        self.entitlement = entitlement


# ---------------------------------------------------------------------------
# Business rule violations
# ---------------------------------------------------------------------------


class ValidationError(DomainError):
    """Request payload fails semantic validation (HTTP 422)."""


class BusinessRuleError(DomainError):
    """General business invariant violated."""


class RateLimitError(DomainError):
    """Too many requests from the same caller within a short window (HTTP 429)."""


class InvalidStateTransitionError(BusinessRuleError):
    """Entity is in a state that does not permit the requested transition."""

    def __init__(self, entity: str, current_state: str, target_state: str) -> None:
        super().__init__(f"Cannot transition {entity} from '{current_state}' to '{target_state}'")
        self.entity = entity
        self.current_state = current_state
        self.target_state = target_state


class ImmutableFieldError(BusinessRuleError):
    """Attempt to modify a field that is immutable after creation."""


class TerminalStateError(BusinessRuleError):
    """Entity is in a terminal state and cannot be modified."""


# ---------------------------------------------------------------------------
# AI errors
# ---------------------------------------------------------------------------


class AIGenerationError(DomainError):
    """LLM generation failed (timeout, parse failure, API error)."""


class AIOutputParseError(AIGenerationError):
    """LLM returned output that could not be parsed into the expected schema."""

    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output
