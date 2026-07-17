"""POST /ai/followups/generate — soạn tin nhắn nhắc khách bằng AI."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.reminders.application.followup_service import FollowUpService
from src.shared.dependencies.ai import AIFacadeDep
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses import ApiResponse

router = APIRouter(tags=["AI"])

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class FollowUpGenerationRequest(BaseModel):
    """Khớp `FollowUpGenerationRequest` trong contracts/openapi.yaml."""

    reminder_type: str = Field(
        description=(
            "follow_up | proposal_follow_up | contract_signing_nudge | payment_due | "
            "payment_overdue | re_engagement | custom"
        )
    )
    target_type: str = Field(description="deal | client | invoice | contract")
    target_id: uuid.UUID
    language: str = "vi"


class FollowUpGenerationResponse(BaseModel):
    """Khớp `FollowUpGenerationResponse` trong contracts/openapi.yaml.

    `subject` là trường THÊM (tiện khi gửi email). Hợp đồng không khoá
    `additionalProperties` nên thêm là hợp lệ, các trường bắt buộc vẫn giữ nguyên.
    """

    message_text: str
    generation_id: str
    subject: str = ""


@router.post(
    "/followups/generate",
    response_model=ApiResponse[FollowUpGenerationResponse],
)
async def generate_followup(
    payload: FollowUpGenerationRequest,
    user_id: CurrentUserId,
    db: DBSession,
    ai: AIFacadeDep,
) -> ApiResponse[FollowUpGenerationResponse]:
    """Soạn BẢN NHÁP tin nhắn nhắc khách — KHÔNG gửi đi.

    Đúng như openapi.yaml mô tả: endpoint này chỉ sinh nội dung, freelancer đọc lại rồi
    tự gửi (hoặc tạo Reminder qua Reminders API). Cố ý không tự động gửi: tin nhắn này
    đi thẳng tới khách hàng, phải có người đọc lại trước.  #Huynh
    """
    result = await FollowUpService(db=db).generate(
        user_id,
        reminder_type=payload.reminder_type,
        target_type=payload.target_type,
        target_id=payload.target_id,
        ai_facade=ai,
    )
    return ApiResponse.ok(FollowUpGenerationResponse(**result))
