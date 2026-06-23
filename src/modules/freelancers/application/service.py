"""Public freelancer directory service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.freelancers.schemas.response import FreelancerCategoryResponse, FreelancerPublicResponse
from src.shared.exceptions.domain import NotFoundError

_CATEGORIES: list[FreelancerCategoryResponse] = [
    FreelancerCategoryResponse(slug="design",      name="Thiết kế",  sub_skills="UI/UX, Logo, Đồ họa, Video"),
    FreelancerCategoryResponse(slug="programming", name="Lập trình", sub_skills="Web, Mobile, Backend, AI"),
    FreelancerCategoryResponse(slug="marketing",   name="Marketing", sub_skills="SEO, Ads, Social Media"),
    FreelancerCategoryResponse(slug="content",     name="Nội dung",  sub_skills="Copywriting, Blog, Kịch bản"),
    FreelancerCategoryResponse(slug="consulting",  name="Tư vấn",    sub_skills="Kinh doanh, Tài chính, Pháp lý"),
]

_NEW_THRESHOLD_DAYS = 30


def _to_response(user, project_count: int) -> FreelancerPublicResponse:
    threshold = datetime.now(UTC) - timedelta(days=_NEW_THRESHOLD_DAYS)
    created = user.created_at
    if created.tzinfo is None:
        from datetime import timezone
        created = created.replace(tzinfo=timezone.utc)
    return FreelancerPublicResponse(
        id=user.id,
        full_name=user.full_name,
        professional_title=user.professional_title,
        bio=user.bio,
        avatar_url=user.avatar_url,
        skills=user.skills or [],
        service_categories=user.service_categories or [],
        portfolio_url=user.portfolio_url,
        rating_average=None,
        rating_count=0,
        completed_project_count=project_count,
        is_new=created >= threshold,
        created_at=user.created_at,
    )


@dataclass
class FreelancersService:
    db: AsyncSession

    def list_categories(self) -> list[FreelancerCategoryResponse]:
        return _CATEGORIES

    async def list_freelancers(
        self,
        q: str | None = None,
        categories: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FreelancerPublicResponse], int]:
        from src.infrastructure.database.models import DealModel, UserModel

        conditions = [
            UserModel.is_listed.is_(True),
            UserModel.status == "active",
            UserModel.deleted_at.is_(None),
        ]
        if q:
            conditions.append(
                or_(
                    UserModel.full_name.ilike(f"%{q}%"),
                    UserModel.bio.ilike(f"%{q}%"),
                    UserModel.professional_title.ilike(f"%{q}%"),
                )
            )
        if categories:
            conditions.append(UserModel.service_categories.overlap(categories))

        total = await self.db.scalar(
            select(func.count()).select_from(UserModel).where(*conditions)
        ) or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(UserModel).where(*conditions)
            .order_by(UserModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        users = list(result.scalars().all())

        # Batch-fetch project counts
        if users:
            user_ids = [u.id for u in users]
            counts_result = await self.db.execute(
                select(DealModel.owner_user_id, func.count(DealModel.id))
                .where(
                    DealModel.owner_user_id.in_(user_ids),
                    DealModel.stage == "completed_and_billed",
                    DealModel.deleted_at.is_(None),
                )
                .group_by(DealModel.owner_user_id)
            )
            count_map: dict[uuid.UUID, int] = {uid: cnt for uid, cnt in counts_result}
        else:
            count_map = {}

        return [_to_response(u, count_map.get(u.id, 0)) for u in users], total

    async def get_freelancer(self, freelancer_id: uuid.UUID) -> FreelancerPublicResponse:
        from src.infrastructure.database.models import DealModel, UserModel

        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.id == freelancer_id,
                UserModel.is_listed.is_(True),
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
        )
        if user is None:
            raise NotFoundError(f"Freelancer {freelancer_id} not found")

        project_count = await self.db.scalar(
            select(func.count(DealModel.id)).where(
                DealModel.owner_user_id == freelancer_id,
                DealModel.stage == "completed_and_billed",
                DealModel.deleted_at.is_(None),
            )
        ) or 0

        return _to_response(user, project_count)
