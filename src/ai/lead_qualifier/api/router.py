from fastapi import APIRouter

from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.lead_qualifier.schemas.request import LeadQualificationRequest
from src.ai.lead_qualifier.schemas.response import LeadQualificationResponse
from src.shared.exceptions.domain import AIGenerationError
from src.shared.responses import ApiResponse

router = APIRouter(tags=["AI"])


@router.post(
    "/leads/qualify",
    response_model=ApiResponse[LeadQualificationResponse],
)
async def qualify_lead(
    request: LeadQualificationRequest,
) -> ApiResponse[LeadQualificationResponse]:
    try:
        result = await LeadQualifier().run(inquiry_text=request.inquiry_text)
    except AIGenerationError:
        raise
    except Exception as exc:
        raise AIGenerationError(str(exc)) from exc
    return ApiResponse.ok(LeadQualificationResponse(**result))
