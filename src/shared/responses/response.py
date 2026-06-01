"""Unified API response envelope."""

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .error import ApiError
from .pagination import PaginationMetadata

T = TypeVar("T")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    code: int
    timestamp: str = Field(default_factory=_now_iso)
    data: T

    @classmethod
    def ok(cls, data: T, code: int = 200) -> "ApiResponse[T]":
        return cls(success=True, code=code, data=data)

    @classmethod
    def created(cls, data: T) -> "ApiResponse[T]":
        return cls.ok(data, code=201)


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    code: int = 200
    timestamp: str = Field(default_factory=_now_iso)
    data: list[T]
    pagination: PaginationMetadata

    @classmethod
    def ok(
        cls,
        data: list[T],
        *,
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        import math
        total_pages = math.ceil(total / page_size) if page_size else 1
        return cls(
            data=data,
            pagination=PaginationMetadata(
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
        )


class ErrorResponse(BaseModel):
    success: bool = False
    code: int
    timestamp: str = Field(default_factory=_now_iso)
    error: ApiError

    @classmethod
    def from_error(
        cls,
        *,
        http_code: int,
        error_code: str,
        message: str,
        details: list | None = None,
    ) -> "ErrorResponse":
        from .error import ValidationErrorDetail
        return cls(
            code=http_code,
            error=ApiError(
                message=message,
                code=error_code,
                details=details or [],
            ),
        )
