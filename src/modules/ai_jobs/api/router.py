import uuid

from fastapi import APIRouter, Query

from src.modules.ai_jobs.application.service import AiJobsService
from src.modules.ai_jobs.schemas.request import AiJobEntityType, CreateAiJobRequest
from src.modules.ai_jobs.schemas.response import AiJobResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.db import DBSession
from src.shared.responses import ApiResponse, PaginatedResponse

router = APIRouter(tags=["AI Jobs"])


@router.post("", response_model=ApiResponse[AiJobResponse], status_code=201)
async def create_job(
    body: CreateAiJobRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[AiJobResponse]:
    service = AiJobsService(db=db)
    job = await service.create_job(user_id, body)
    return ApiResponse.created(AiJobResponse.model_validate(job))


@router.get("", response_model=PaginatedResponse[AiJobResponse])
async def list_jobs(
    user_id: CurrentUserId,
    db: DBSession,
    entity_type: AiJobEntityType | None = Query(default=None, description="Filter by entity_type"),
    entity_id: uuid.UUID | None = Query(default=None, description="Filter by entity_id"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[AiJobResponse]:
    jobs, total = await AiJobsService(db=db).list_jobs(
        user_id, entity_type=entity_type, entity_id=entity_id, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [AiJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=ApiResponse[AiJobResponse])
async def get_job(
    job_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[AiJobResponse]:
    service = AiJobsService(db=db)
    job = await service.get_job(user_id, job_id)
    return ApiResponse.ok(AiJobResponse.model_validate(job))


@router.post("/{job_id}/cancel", response_model=ApiResponse[AiJobResponse])
async def cancel_job(
    job_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[AiJobResponse]:
    service = AiJobsService(db=db)
    job = await service.cancel_job(user_id, job_id)
    return ApiResponse.ok(AiJobResponse.model_validate(job))
