"""Proposals API api."""

import uuid
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.proposals.application.service import ProposalsService
from src.modules.proposals.domain.value_objects.proposal_status import ProposalStatus
from src.modules.proposals.schemas.request import (
    AiProposalRequest,
    CreateProposalRequest,
    ProposalPriceRequest,
    ProposalStatusRequest,
    UpdateProposalRequest,
)
from src.modules.proposals.schemas.response import ProposalResponse, TermTemplateOption
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.domain.template_blocks import (
    skeleton_block_labels,
    template_block_labels,
    template_preview,
)
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("/ai-generate", response_model=ApiResponse[ProposalResponse], status_code=201)
async def ai_generate_proposal(
    payload: AiProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
) -> ApiResponse[ProposalResponse]:
    """Sinh báo giá bằng AI cho một deal.

    Endpoint này giờ đi CHUNG một đường với `/generate-from-deal`: cả hai đều dựng ngữ
    cảnh từ database (deal + phiếu tiếp nhận của khách + hồ sơ freelancer).

    Vì sao đổi: trước đây nó KHÔNG đọc database, chỉ dùng đúng những gì frontend nhét vào
    payload. Mà frontend thì gửi `project_description = ghi chú nội bộ` và KHÔNG hề gửi
    nguyên văn yêu cầu của khách — dù nó nằm sẵn trong bảng `deal_intakes`. Kết quả: khách
    viết cả đoạn mô tả mà báo giá vẫn mỏng dính, vì AI bị bịt mắt.

    Các trường trong payload giờ là dư thừa (đều suy ra được từ `deal_id`), nhưng vẫn nhận
    để không phá hợp đồng API. Nguồn sự thật là DATABASE, không phải payload.  #Huynh
    """
    proposal = await ProposalsService(db=db).generate_from_deal(
        user_id, payload.deal_id, ai, template_id=payload.template_id
    )
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.post(
    "/generate-from-deal/{deal_id}",
    response_model=ApiResponse[ProposalResponse],
    status_code=201,
)
async def generate_proposal_from_deal(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
    template_id: uuid.UUID | None = Query(default=None),
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).generate_from_deal(
        user_id, deal_id, ai, template_id=template_id
    )
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.post(
    "/from-template/{deal_id}",
    response_model=ApiResponse[ProposalResponse],
    status_code=201,
)
async def create_proposal_from_template(
    deal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    template_id: uuid.UUID | None = Query(default=None),
) -> ApiResponse[ProposalResponse]:
    """Soạn báo giá từ KHUNG mẫu — đường thứ hai, không đi qua AI.

    CỐ Ý không có `AIFacadeDep` trong chữ ký: đây là điểm khác biệt duy nhất so với
    `generate-from-deal` ngay trên, và cũng là lý do endpoint này tồn tại. Không tốn lượt AI,
    chạy được với gói Free.

    `template_id` để trống = "khung trắng": bản nháp rỗng với đủ ô để freelancer tự điền.  #Huynh
    """
    proposal = await ProposalsService(db=db).create_from_template(
        user_id, deal_id, template_id=template_id
    )
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.get("/term-templates", response_model=ApiResponse[list[TermTemplateOption]])
async def list_proposal_term_templates(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[TermTemplateOption]]:
    """Mẫu điều khoản báo giá freelancer được chọn (theo nghề của họ + dùng chung, đang bật).

    Freelancer gọi được (khác `/admin/templates` chỉ admin). FE dùng để dựng danh sách chọn
    trước khi sinh báo giá.
    """
    templates = await ProposalsService(db=db).list_term_templates(user_id)
    return ApiResponse.ok(
        [
            TermTemplateOption(
                id=t.id,
                name=t.name,
                profession=t.profession,
                blocks=template_block_labels(t.content, "proposal"),
                preview=template_preview(t.content, "proposal"),
                skeleton_blocks=skeleton_block_labels(t.content, "proposal"),
            )
            for t in templates
        ]
    )


@router.patch("/{proposal_id}/price", response_model=ApiResponse[ProposalResponse])
async def set_proposal_price(
    proposal_id: uuid.UUID,
    payload: ProposalPriceRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    """Freelancer chốt giá cuối cùng. AI chỉ đề xuất khoảng — con người quyết con số."""
    proposal = await ProposalsService(db=db).set_price(user_id, proposal_id, payload.price)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


class ProposalPreviewResponse(BaseModel):
    html: str


@router.get("/{proposal_id}/preview", response_model=ApiResponse[ProposalPreviewResponse])
async def preview_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    editable: bool = Query(
        default=False,
        description="True: render thêm ô rỗng cho mục chưa có nội dung, để sửa tại chỗ (bản nháp).",
    ),
) -> ApiResponse[ProposalPreviewResponse]:
    """HTML xem trước — CHÍNH XÁC bản PDF khách sẽ nhận.

    Frontend nhúng HTML này vào card thay vì tự dựng lại. Cùng một template với PDF nên
    hai bên KHÔNG THỂ lệch nhau — đó là cái gốc khiến bản trên màn hình trước đây khác bản
    tải về, nhìn như lừa đảo.  #Huynh
    """
    html = await ProposalsService(db=db).render_preview_html(
        user_id, proposal_id, editable=editable
    )
    return ApiResponse.ok(ProposalPreviewResponse(html=html))


@router.get("/{proposal_id}/pdf")
async def generate_proposal_pdf(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
):
    pdf_bytes = await ProposalsService(db=db).generate_pdf(
        user_id=user_id,
        proposal_id=proposal_id,
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": (f'attachment; filename="proposal-{proposal_id}.pdf"')},
    )


@router.post("", response_model=ApiResponse[ProposalResponse], status_code=201)
async def create_proposal(
    payload: CreateProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).create(user_id, payload)
    return ApiResponse.created(ProposalResponse.model_validate(proposal))


@router.get("", response_model=PaginatedResponse[ProposalResponse])
async def list_proposals(
    user_id: CurrentUserId,
    db: DBSession,
    status: ProposalStatus | None = Query(
        default=None,
        description="Filter by status: draft, sent, accepted, rejected, expired, superseded",
    ),
    deal_id: uuid.UUID | None = Query(default=None, description="Filter by deal"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[ProposalResponse]:
    proposals, total = await ProposalsService(db=db).list_all(
        user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
    )
    return PaginatedResponse.ok(
        [ProposalResponse.model_validate(p) for p in proposals],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{proposal_id}", response_model=ApiResponse[ProposalResponse])
async def get_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).get_one(user_id, proposal_id)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.patch("/{proposal_id}", response_model=ApiResponse[ProposalResponse])
async def update_proposal(
    proposal_id: uuid.UUID,
    payload: UpdateProposalRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).update(user_id, proposal_id, payload)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.post("/{proposal_id}/generate", response_model=ApiResponse[ProposalResponse])
async def ai_generate_proposal_content(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).generate_content(user_id, proposal_id, ai)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.post("/{proposal_id}/send", response_model=ApiResponse[ProposalResponse])
async def send_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).transition_status(user_id, proposal_id, "sent")
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.patch("/{proposal_id}/status", response_model=ApiResponse[ProposalResponse])
async def transition_proposal_status(
    proposal_id: uuid.UUID,
    payload: ProposalStatusRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ProposalResponse]:
    proposal = await ProposalsService(db=db).transition_status(user_id, proposal_id, payload.status)
    return ApiResponse.ok(ProposalResponse.model_validate(proposal))


@router.delete("/{proposal_id}", response_model=ApiResponse[MsgResp])
async def delete_proposal(
    proposal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ProposalsService(db=db).delete(user_id, proposal_id)
    return ApiResponse.ok(MsgResp(detail="Proposal deleted"))
