"""Deals API api."""

import uuid
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.deals.application.attachment_service import DealAttachmentService
from src.modules.deals.application.service import DealsService
from src.modules.deals.domain.entities.deal_activity import DealActivityType
from src.modules.deals.domain.value_objects.deal_stage import DealStage
from src.modules.deals.schemas.request import AddNoteRequest, DealRequest, DealStageRequest
from src.modules.deals.schemas.response import (
    DealActivityEntryResponse,
    DealAttachmentResponse,
    DealResponse,
    IntakeResponse,
    LeadScoreHistoryResponse,
)
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.storage import StorageDep
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[DealResponse], status_code=201)
async def create_deal(
    payload: DealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).create(user_id, payload)
    return ApiResponse.created(DealResponse.model_validate(deal))


@router.get("", response_model=PaginatedResponse[DealResponse])
async def list_deals(
    user_id: CurrentUserId,
    db: DBSession,
    title: str | None = Query(
        default=None, description="Search by title (case-insensitive, partial match)"
    ),
    stage: DealStage | None = Query(
        default=None,
        description="Filter by stage: new_lead, qualified, proposal_sent, in_negotiation, active, completed_and_billed, lost",
    ),
    client_id: uuid.UUID | None = Query(
        default=None, description="Filter by client ID"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[DealResponse]:
    deals, total = await DealsService(db=db).list_all(
        user_id, title=title, stage=stage, client_id=client_id, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [DealResponse.model_validate(d) for d in deals], total=total, page=page, page_size=page_size
    )


@router.get("/intakes", response_model=PaginatedResponse[IntakeResponse])
async def list_intakes(
    user_id: CurrentUserId,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[IntakeResponse]:
    intakes, total = await DealsService(db=db).list_intakes(user_id, page=page, page_size=page_size)
    return PaginatedResponse.ok(
        [IntakeResponse.model_validate(i) for i in intakes],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/intakes/{intake_id}", response_model=ApiResponse[IntakeResponse])
async def get_intake(
    intake_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[IntakeResponse]:
    intake = await DealsService(db=db).get_intake(user_id, intake_id)
    return ApiResponse.ok(IntakeResponse.model_validate(intake))



@router.get("/{deal_id}", response_model=ApiResponse[DealResponse])
async def get_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).get_one(user_id, deal_id)
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.patch("/{deal_id}", response_model=ApiResponse[DealResponse])
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).update(user_id, deal_id, payload)
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.delete("/{deal_id}", response_model=ApiResponse[MsgResp])
async def delete_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await DealsService(db=db).delete(user_id, deal_id)
    return ApiResponse.ok(MsgResp(detail="Deal deleted"))


@router.post(
    "/{deal_id}/document",
    response_model=ApiResponse[DealResponse],
    summary="Upload a PDF document to a deal",
)
async def upload_document(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
) -> ApiResponse[DealResponse]:
    content = await file.read()
    deal = await DealsService(db=db, storage=storage).upload_document(
        user_id,
        deal_id,
        filename=file.filename or "document.pdf",
        content=content,
        content_type=file.content_type or "",
    )
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.get(
    "/{deal_id}/qualifications",
    response_model=ApiResponse[list[LeadScoreHistoryResponse]],
)
async def list_deal_qualifications(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[LeadScoreHistoryResponse]]:
    """Lịch sử chấm điểm của deal — mới nhất trước, kèm bảng căn cứ.

    Thay cho localStorage: kết quả chấm điểm là căn cứ ra quyết định tiền bạc, để ở trình
    duyệt là đổi máy/xoá cache thì mất.  #Huynh
    """
    rows = await DealsService(db=db).list_qualifications(user_id, deal_id)
    return ApiResponse.ok([LeadScoreHistoryResponse.model_validate(r) for r in rows])


@router.post("/{deal_id}/qualify")
async def qualify_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
):
    result = await DealsService(db=db, ai_facade=ai).qualify_deal(user_id, deal_id)
    return ApiResponse.ok(result)


@router.post("/{deal_id}/stage", response_model=ApiResponse[DealResponse])
async def transition_stage(
    deal_id: uuid.UUID,
    payload: DealStageRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealResponse]:
    deal = await DealsService(db=db).transition_stage(user_id, deal_id, payload)
    return ApiResponse.ok(DealResponse.model_validate(deal))


@router.get("/{deal_id}/activity", response_model=PaginatedResponse[DealActivityEntryResponse])
async def list_deal_activity(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    entry_type: DealActivityType | None = Query(
        default=None, description="Filter by activity type"
    ),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[DealActivityEntryResponse]:
    entries, total = await DealsService(db=db).list_activity(
        user_id,
        deal_id,
        entry_type=entry_type.value if entry_type else None,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.ok(
        [DealActivityEntryResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{deal_id}/notes",
    response_model=ApiResponse[DealActivityEntryResponse],
    status_code=201,
)
async def add_deal_note(
    deal_id: uuid.UUID,
    payload: AddNoteRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[DealActivityEntryResponse]:
    entry = await DealsService(db=db).add_note(user_id, deal_id, payload.description)
    return ApiResponse.created(DealActivityEntryResponse.model_validate(entry))


# ---------------------------------------------------------------------------
# File đính kèm — khách gửi brief PDF, AI đọc để chấm điểm deal
# ---------------------------------------------------------------------------


# `DealAttachmentResponse` đã dời sang `schemas/response.py` (đúng chỗ theo AGENTS.md): giờ
# đường CÔNG KHAI của biểu mẫu cũng trả cùng shape này, mà router import router thì rối.


@router.post(
    "/{deal_id}/attachments",
    response_model=ApiResponse[DealAttachmentResponse],
    status_code=201,
)
async def upload_deal_attachment(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    file: UploadFile = File(...),
) -> ApiResponse[DealAttachmentResponse]:
    """Đính file vào deal (brief dự án khách gửi, hợp đồng scan, biên nhận...).

    File PDF sẽ được BÓC CHỮ ngay lúc upload và lưu vào DB. Khi chấm điểm deal, chữ đó
    được đưa vào khối "KHÁCH HÀNG NÓI GÌ" của prompt — nên AI đọc được yêu cầu thật của
    khách thay vì chỉ thấy mỗi cái tên dự án.  #Huynh
    """
    data = await file.read()
    attachment = await DealAttachmentService(db=db).upload(
        user_id,
        deal_id,
        filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return ApiResponse.created(DealAttachmentResponse.from_model(attachment))


@router.get(
    "/{deal_id}/attachments",
    response_model=ApiResponse[list[DealAttachmentResponse]],
)
async def list_deal_attachments(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[DealAttachmentResponse]]:
    rows = await DealAttachmentService(db=db).list_for_deal(user_id, deal_id)
    return ApiResponse.ok([DealAttachmentResponse.from_model(r) for r in rows])


@router.get("/attachments/{attachment_id}/download")
async def download_deal_attachment(
    attachment_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
):
    data, content_type, filename = await DealAttachmentService(db=db).download(
        user_id, attachment_id
    )
    return StreamingResponse(
        BytesIO(data),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/attachments/{attachment_id}", response_model=ApiResponse[MsgResp])
async def delete_deal_attachment(
    attachment_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await DealAttachmentService(db=db).delete(user_id, attachment_id)
    return ApiResponse.ok(MsgResp(detail="Attachment deleted"))
