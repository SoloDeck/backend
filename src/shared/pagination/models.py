import math

from fastapi import Query
from pydantic import BaseModel, computed_field


class PaginationParams:
    """FastAPI dependency for pagination query parameters."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))


class Page[T](BaseModel):
    items: list[T]
    pagination: PaginationMeta

    @classmethod
    def create(cls, items: list[T], total: int, params: PaginationParams) -> "Page[T]":
        return cls(
            items=items,
            pagination=PaginationMeta(
                total=total,
                page=params.page,
                page_size=params.page_size,
            ),
        )
