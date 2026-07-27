from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.lead_qualifier.schemas.request import LeadQualificationRequest
from src.ai.lead_qualifier.schemas.response import LeadQualificationResponse
from src.infrastructure.database.session import get_db_session
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.dependencies.auth import CurrentUserId
from src.shared.exceptions.domain import AIGenerationError
from src.shared.responses import ApiResponse

router = APIRouter(tags=["AI"])

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "/leads/qualify",
    response_model=ApiResponse[LeadQualificationResponse],
)
async def qualify_lead(
    request: LeadQualificationRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[LeadQualificationResponse]:
    """Chấm điểm một lead (bản standalone).

    Endpoint này TRƯỚC ĐÂY KHÔNG ĐÒI TOKEN — không có `CurrentUserId`, không `Depends`
    nào. Bất kỳ ai trên internet cũng gọi được, và **mỗi lần gọi là đốt quota Groq của
    chủ hệ thống**. Chỉ cần một vòng lặp curl là hết tiền AI.

    `openapi.yaml` khai rõ ở tag AI: *"All require an AI-enabled subscription"* — code
    không làm theo. Giờ đòi đăng nhập, kiểm tra gói, và ghi nhận lượt dùng.  #Huynh
    """
    await AiUsageService(db=db).consume(user_id)

    try:
        result = await LeadQualifier().run(inquiry_text=request.inquiry_text)
    except AIGenerationError:
        raise
    except Exception as exc:
        raise AIGenerationError(str(exc)) from exc
    return ApiResponse.ok(LeadQualificationResponse(**result))
