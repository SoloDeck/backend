"""Maps domain exceptions raised inside an AI job's Celery task to a JobError.

Mirrors the code/status mapping in src/shared/exceptions/http.py, plus a
`retryable` verdict: True for failures a repeated attempt could plausibly
fix (rate limits, transient LLM errors), False for failures that will keep
happening until something about the request changes.

Ngoài các lỗi nghiệp vụ (DomainError), còn một nhánh riêng cho lỗi do CHÍNH nhà cung cấp
mô hình trả về — xem `_to_provider_error`. Nhánh này tồn tại vì lỗi hạ tầng AI trước đây
rơi hết vào nhánh mặc định "An unexpected error occurred", làm mất sạch nguyên nhân thật.
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

    provider_error = _to_provider_error(exc)
    if provider_error is not None:
        return provider_error

    return JobError(
        code=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="An unexpected error occurred",
        retryable=False,
    )


# Câu giải thích theo mã HTTP mà nhà cung cấp mô hình trả về. Viết bằng tiếng Việt và nói
# thẳng phải làm gì, vì đây là câu người trực buổi demo đọc to lên cho hội đồng nghe.
_PROVIDER_HTTP_MESSAGES: dict[int, str] = {
    400: "Nhà cung cấp AI từ chối nội dung gửi sang (yêu cầu không hợp lệ).",
    401: "Khoá API của nhà cung cấp AI không hợp lệ hoặc đã hết hạn.",
    403: "Khoá API của nhà cung cấp AI không có quyền gọi mô hình này.",
    404: "Mô hình AI đang cấu hình không còn được nhà cung cấp phục vụ.",
    413: (
        "Nội dung gửi sang AI vượt hạn mức token mỗi phút của gói nhà cung cấp. "
        "Cần rút gọn dữ liệu deal, nâng gói bên nhà cung cấp, hoặc đổi sang mô hình khác."
    ),
    429: "Nhà cung cấp AI đang quá tải hoặc đã chạm hạn mức gọi. Chờ một lát rồi thử lại.",
    500: "Nhà cung cấp AI gặp sự cố nội bộ.",
    502: "Nhà cung cấp AI gặp sự cố nội bộ.",
    503: "Nhà cung cấp AI đang tạm ngừng phục vụ.",
    504: "Nhà cung cấp AI phản hồi quá chậm nên bị ngắt giữa chừng.",
}

# Sai cấu hình thì gọi lại bao nhiêu lần cũng thế — đừng để worker thử lại 3 lần cho phí,
# và đừng để màn hình khuyên người dùng "bấm thử lại sau ít phút".
_PROVIDER_NOT_RETRYABLE: frozenset[int] = frozenset({400, 401, 403, 404})

_PROVIDER_DETAIL_LIMIT = 300


def _to_provider_error(exc: Exception) -> JobError | None:
    """Nhận diện lỗi do CHÍNH nhà cung cấp mô hình trả về (Groq / Gemini / OpenAI).

    Ba SDK không có lớp exception chung, nhưng đều gắn mã HTTP vào thuộc tính ``status_code``
    (Groq, OpenAI) hoặc ``code`` (google-genai). Bắt bằng thuộc tính thay vì ``isinstance``
    để module này không phải import SDK nào — thêm nhà cung cấp thứ tư vẫn chạy.

    Trả ``None`` khi không phải lỗi nhà cung cấp, để hàm gọi rơi tiếp xuống nhánh mặc định.

    Vì sao cần: trước đây mọi lỗi lạ đều thành "An unexpected error occurred" +
    ``retryable=False``, mà giao diện lại dịch ``retryable=False`` thành "bạn cần nâng cấp
    gói". Groq chặn vì token thì màn hình đổ tội cho gói dịch vụ — sai người, sai bệnh, và
    lúc demo thì không giải thích nổi.  #Huynh
    """
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(exc, "code", None)
    if not isinstance(status, int) or not 400 <= status <= 599:
        return None

    message = _PROVIDER_HTTP_MESSAGES.get(status, f"Nhà cung cấp AI trả về lỗi {status}.")

    # Giữ lại nguyên văn của nhà cung cấp, cắt ngắn cho vừa một dòng đọc được: đây là thứ
    # duy nhất chỉ đúng thủ phạm khi ngồi dò lỗi ("TPM: Limit 8000, Requested 8462").
    detail = " ".join(str(exc).split())
    if detail:
        if len(detail) > _PROVIDER_DETAIL_LIMIT:
            detail = f"{detail[:_PROVIDER_DETAIL_LIMIT]}…"
        message = f"{message} (Nhà cung cấp báo: {detail})"

    return JobError(
        code=ErrorCode.AI_PROVIDER_ERROR.value,
        message=message,
        retryable=status not in _PROVIDER_NOT_RETRYABLE,
    )
