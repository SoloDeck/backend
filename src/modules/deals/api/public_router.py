"""Public deal-intake endpoint — no authentication required.

Mounted at `/api/v1/intake`. A client self-submits a lead via the owner's
hard-to-guess share token; the owner is resolved from that token alone.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.deals.application.service import DealsService
from src.modules.deals.schemas.request import PublicIntakeRequest
from src.modules.deals.schemas.response import (
    DealAttachmentResponse,
    PublicIntakeResponse,
)
from src.modules.intake_form.application.service import IntakeFormService
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "/{share_token}",
    response_model=ApiResponse[PublicIntakeResponse],
    status_code=201,
    summary="Submit a public intake request",
    description=(
        "Allows a potential client to submit a project inquiry directly to a freelancer. "
        "The `share_token` identifies the freelancer who owns the intake form. "
        "Required fields are validated against the freelancer's saved form configuration. "
        "On success, a new Deal is created in the freelancer's CRM and AI lead scoring is triggered asynchronously. "
        "No authentication required."
    ),
)
async def submit_public_intake(
    share_token: str,
    payload: PublicIntakeRequest,
    db: DBSession,
) -> ApiResponse[PublicIntakeResponse]:
    """Validate required fields against the form config, then create a Deal from the intake submission."""
    await IntakeFormService(db=db).validate_submission(share_token, payload)
    intake = await DealsService(db=db).create_public_intake(share_token, payload)
    return ApiResponse.created(PublicIntakeResponse.model_validate(intake))


@router.post(
    "/{share_token}/{intake_id}/attachments",
    response_model=ApiResponse[DealAttachmentResponse],
    status_code=201,
    summary="Attach a file to a just-submitted intake",
    description=(
        "Lets the client attach a file to the inquiry they just submitted — no authentication. "
        "Call once per file, right after `POST /intake/{share_token}`. "
        "Guarded by a per-link rate limit, a 15-minute window after submission and a cap of 10 "
        "files per inquiry; file type and size limits are the same as the authenticated upload."
    ),
)
async def upload_public_intake_attachment(
    share_token: str,
    intake_id: uuid.UUID,
    db: DBSession,
    file: UploadFile = File(...),
) -> ApiResponse[DealAttachmentResponse]:
    """Nhận tệp khách gửi kèm biểu mẫu.

    Tệp đi SAU phiếu (phiếu tạo xong mới có id để gắn vào), nên đây là lệnh gọi riêng chứ
    không nhét vào cùng body JSON của form.  #Huynh
    """
    data = await file.read()
    attachment = await DealsService(db=db).add_public_intake_attachment(
        share_token,
        intake_id,
        filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return ApiResponse.created(DealAttachmentResponse.from_model(attachment))
