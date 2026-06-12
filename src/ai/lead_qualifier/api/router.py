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

router = APIRouter(tags=["AI"])


@router.post(
    "/leads/qualify",
    response_model=LeadQualificationResponse
)
def qualify_lead(
    request: LeadQualificationRequest
):

    result = LeadQualifierService.qualify(
        request.inquiry_text
    )

    return result