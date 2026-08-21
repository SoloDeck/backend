"""Contracts API api."""

import uuid
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.contracts.application.service import ContractsService
from src.modules.contracts.domain.value_objects.contract_status import ContractStatus
from src.modules.contracts.schemas.request import (
    ContractStatusRequest,
    ContractTerminateRequest,
    CreateContractRequest,
    CreatePaymentMilestoneRequest,
    UpdateContractRequest,
    UpdatePaymentMilestoneRequest,
)
from src.modules.contracts.schemas.response import (
    ContractExportResponse,
    ContractResponse,
    PaymentMilestoneResponse,
    TermTemplateOption,
)
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.domain.template_blocks import (
    skeleton_block_labels,
    template_block_labels,
    template_preview,
)
from src.shared.pagination.models import PaginationParams
from src.shared.responses.response import ApiResponse, PaginatedResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


class ContractPreviewResponse(BaseModel):
    html: str


@router.get("", response_model=PaginatedResponse[ContractResponse])
async def list_contracts(
    user_id: CurrentUserId,
    db: DBSession,
    pagination: Annotated[PaginationParams, Depends()],
    status: ContractStatus | None = Query(
        default=None,
        description="Filter by status: draft, pending_signatures, active, completed, terminated, expired, archived",
    ),
    deal_id: uuid.UUID | None = Query(default=None, description="Filter by deal"),
) -> PaginatedResponse[ContractResponse]:
    contracts, total = await ContractsService(db=db).list_all(
        user_id,
        status=status,
        deal_id=deal_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse.ok(
        [ContractResponse.model_validate(c) for c in contracts],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=ApiResponse[ContractResponse], status_code=201)
async def create_contract(
    payload: CreateContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).create(user_id, payload)
    return ApiResponse.created(ContractResponse.model_validate(contract))


# PHẢI khai TRƯỚC "/{contract_id}" — để sau thì "term-templates" bị nuốt vào route động
# và trả 422 vì không phải UUID.  #Huynh
@router.get("/term-templates", response_model=ApiResponse[list[TermTemplateOption]])
async def list_contract_term_templates(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[TermTemplateOption]]:
    """Mẫu điều khoản hợp đồng freelancer được chọn (theo nghề + dùng chung, đang bật)."""
    templates = await ContractsService(db=db).list_term_templates(user_id)
    return ApiResponse.ok(
        [
            TermTemplateOption(
                id=t.id,
                name=t.name,
                profession=t.profession,
                blocks=template_block_labels(t.content, "contract"),
                preview=template_preview(t.content, "contract"),
                skeleton_blocks=skeleton_block_labels(t.content, "contract"),
            )
            for t in templates
        ]
    )


@router.get("/{contract_id}", response_model=ApiResponse[ContractResponse])
async def get_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).get_one(user_id, contract_id)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.get("/{contract_id}/preview", response_model=ApiResponse[ContractPreviewResponse])
async def preview_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    editable: bool = Query(
        default=False,
        description="True: render thêm ô rỗng cho điều khoản chưa có, để sửa tại chỗ (bản nháp).",
    ),
) -> ApiResponse[ContractPreviewResponse]:
    """HTML xem trước — CHÍNH XÁC bản hợp đồng khách sẽ nhận/ký.

    Frontend nhúng HTML này vào iframe thay vì tự dựng lại từ các trường thô. Cùng một
    template với bản PDF nên hai bên KHÔNG THỂ lệch — đó là gốc khiến tờ hợp đồng trên
    màn hình trước đây trông sơ sài, không giống một hợp đồng thật.  #Huynh
    """
    html = await ContractsService(db=db).render_preview_html(
        user_id, contract_id, editable=editable
    )
    return ApiResponse.ok(ContractPreviewResponse(html=html))


@router.get("/{contract_id}/pdf")
async def download_contract_pdf(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
):
    """Tải PDF hợp đồng (render đồng bộ) — freelancer gửi cho khách. Cùng document với bản
    xem trước nên PDF = đúng thứ trên màn hình. Cùng khuôn với GET /proposals/{id}/pdf.  #Huynh
    """
    pdf_bytes = await ContractsService(db=db).generate_pdf(user_id, contract_id)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="contract-{contract_id}.pdf"'},
    )


@router.patch("/{contract_id}", response_model=ApiResponse[ContractResponse])
async def update_contract(
    contract_id: uuid.UUID,
    payload: UpdateContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).update(user_id, contract_id, payload)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/generate", response_model=ApiResponse[ContractResponse])
async def ai_generate_contract_content(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
    template_id: uuid.UUID | None = Query(default=None),
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).generate_content(
        user_id, contract_id, ai, template_id=template_id
    )
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/from-template", response_model=ApiResponse[ContractResponse])
async def fill_contract_from_template(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    template_id: uuid.UUID | None = Query(default=None),
) -> ApiResponse[ContractResponse]:
    """Điền hợp đồng từ KHUNG mẫu — đường thứ hai, không đi qua AI.

    Song sinh với `/generate` ngay trên, khác đúng một chỗ: không có `AIFacadeDep`. Frontend đổi
    một lời gọi là chuyển được chế độ.  #Huynh
    """
    contract = await ContractsService(db=db).fill_from_template(
        user_id, contract_id, template_id=template_id
    )
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/amend", response_model=ApiResponse[ContractResponse], status_code=201)
async def amend_contract(
    contract_id: uuid.UUID,
    payload: UpdateContractRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).amend(user_id, contract_id, payload)
    return ApiResponse.created(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/send", response_model=ApiResponse[ContractResponse])
async def send_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).send(user_id, contract_id)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/sign", response_model=ApiResponse[ContractResponse])
async def sign_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).sign(user_id, contract_id)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.post("/{contract_id}/terminate", response_model=ApiResponse[ContractResponse])
async def terminate_contract(
    contract_id: uuid.UUID,
    payload: ContractTerminateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).terminate(user_id, contract_id)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.patch("/{contract_id}/status", response_model=ApiResponse[ContractResponse])
async def transition_contract_status(
    contract_id: uuid.UUID,
    payload: ContractStatusRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractResponse]:
    contract = await ContractsService(db=db).transition_status(user_id, contract_id, payload.status)
    return ApiResponse.ok(ContractResponse.model_validate(contract))


@router.get(
    "/{contract_id}/milestones", response_model=ApiResponse[list[PaymentMilestoneResponse]]
)
async def list_milestones(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[PaymentMilestoneResponse]]:
    milestones = await ContractsService(db=db).list_milestones(user_id, contract_id)
    return ApiResponse.ok([PaymentMilestoneResponse.model_validate(m) for m in milestones])


@router.post(
    "/{contract_id}/milestones",
    response_model=ApiResponse[PaymentMilestoneResponse],
    status_code=201,
)
async def add_milestone(
    contract_id: uuid.UUID,
    payload: CreatePaymentMilestoneRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[PaymentMilestoneResponse]:
    milestone = await ContractsService(db=db).add_milestone(user_id, contract_id, payload)
    return ApiResponse.created(PaymentMilestoneResponse.model_validate(milestone))


@router.patch(
    "/{contract_id}/milestones/{milestone_id}",
    response_model=ApiResponse[PaymentMilestoneResponse],
)
async def update_milestone(
    contract_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: UpdatePaymentMilestoneRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[PaymentMilestoneResponse]:
    milestone = await ContractsService(db=db).update_milestone(
        user_id, contract_id, milestone_id, payload
    )
    return ApiResponse.ok(PaymentMilestoneResponse.model_validate(milestone))


@router.delete("/{contract_id}/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    contract_id: uuid.UUID,
    milestone_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> None:
    await ContractsService(db=db).delete_milestone(user_id, contract_id, milestone_id)


@router.get("/{contract_id}/export", response_model=ApiResponse[ContractExportResponse])
async def export_contract_pdf(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ContractExportResponse]:
    result = await ContractsService(db=db).export_pdf(user_id, contract_id)
    return ApiResponse.ok(ContractExportResponse(**result))


@router.delete("/{contract_id}", response_model=ApiResponse[MsgResp])
async def delete_contract(
    contract_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await ContractsService(db=db).delete(user_id, contract_id)
    return ApiResponse.ok(MsgResp(detail="Contract deleted"))
