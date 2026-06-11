from fastapi import APIRouter

from src.ai.lead_qualifier.schemas.request import (
    LeadQualificationRequest
)

from src.ai.lead_qualifier.schemas.response import (
    LeadQualificationResponse
)

from src.ai.lead_qualifier.application.service import (
    LeadQualifierService
)

router = APIRouter(
    prefix="/ai/lead-qualifier",
    tags=["Lead Qualifier"]
)


@router.post(
    "",
    response_model=LeadQualificationResponse
)
def qualify_lead(
    request: LeadQualificationRequest
):

    result = LeadQualifierService.qualify(
        request.inquiry_text
    )

    return result