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
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
    value: Any = None


class ApiError(BaseModel):
    message: str
    code: str
    details: list[ValidationErrorDetail] = []
