"""Public freelancer directory — no authentication required."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.freelancers.application.service import FreelancersService
from src.modules.freelancers.schemas.response import FreelancerCategoryResponse, FreelancerPublicResponse
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/categories", response_model=ApiResponse[list[FreelancerCategoryResponse]])
async def list_categories(
    db: DBSession,
) -> ApiResponse[list[FreelancerCategoryResponse]]:
    categories = FreelancersService(db=db).list_categories()
    return ApiResponse.ok(categories)


@router.get("", response_model=PaginatedResponse[FreelancerPublicResponse])
async def search_freelancers(
    db: DBSession,
    q: str | None = Query(default=None, description="Search by name, title, or bio"),
    categories: list[str] | None = Query(default=None, description="Filter by category slugs: design, programming, marketing, content, consulting"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[FreelancerPublicResponse]:
    freelancers, total = await FreelancersService(db=db).list_freelancers(
        q=q, categories=categories, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(freelancers, total=total, page=page, page_size=page_size)


@router.get("/{freelancer_id}", response_model=ApiResponse[FreelancerPublicResponse])
async def get_freelancer(
    freelancer_id: uuid.UUID,
    db: DBSession,
) -> ApiResponse[FreelancerPublicResponse]:
    freelancer = await FreelancersService(db=db).get_freelancer(freelancer_id)
    return ApiResponse.ok(freelancer)
