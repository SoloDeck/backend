"""Pagination metadata model."""

from pydantic import BaseModel


class PaginationMetadata(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
