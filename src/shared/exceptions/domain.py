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
# Hạ tầng bên ngoài
# ---------------------------------------------------------------------------


class EmailDeliveryError(DomainError):
    """Không gửi được email qua SMTP.

    Sinh ra vì lỗi SMTP trước đây rơi thẳng vào `@app.exception_handler(Exception)` →
    `500 INTERNAL_SERVER_ERROR` + "An unexpected error occurred", **không phân biệt được
    với hỏng database**. Màn hình quên mật khẩu vì thế chỉ nói được một câu chung chung,
    và lần truy lỗi nào cũng phải bắt đầu bằng việc đoán.

    `reason` là thứ frontend và log cùng dựa vào để phân nhánh — quan trọng nhất là tách
    `quota` (thử lại sau vài giờ là được) khỏi `auth` (thử lại bao nhiêu lần cũng vô ích,
    phải sửa cấu hình). Gộp hai cái đó vào một câu "thử lại sau ít phút" là bảo người dùng
    làm một việc chắc chắn vô nghĩa.

    Giá trị: ``auth`` · ``quota`` · ``connect`` · ``unknown``.  #Huynh
    """

    def __init__(self, message: str, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


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
