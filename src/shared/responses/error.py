"""Standardised error envelope and error codes."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED"
    AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    # Gửi email thất bại. Tách riêng khỏi INTERNAL_SERVER_ERROR để frontend phân biệt được
    # "hệ thống thư hỏng" với "server sập" — hai chuyện đó cần hai câu khác nhau, và trước
    # đây cả hai đều rơi vào cùng một mã nên màn hình chỉ nói được một câu chung chung.
    #
    # Frontend nhận biết bằng MÃ NÀY, không so khớp câu tiếng Việt: đổi câu chữ mà làm gãy
    # luồng xử lý lỗi thì lần sau không ai dám sửa câu chữ nữa.  #Huynh
    EMAIL_DELIVERY_FAILED = "EMAIL_DELIVERY_FAILED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    value: Any = None


class ApiError(BaseModel):
    message: str
    code: str
    details: list[ValidationErrorDetail] = Field(default_factory=list)
