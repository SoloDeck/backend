from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from google import genai

from src.config.settings import settings

from ..application.service import (
    ProposalGenerationService
)

from ..application.render import (
    ProposalPdfRenderer
)

from ..schemas.ProposalGenerationInput import (
    ProposalGenerationInput
)

from ..schemas.ProposalContent import (
    ProposalContent
)

from ..schemas.ProposalDocument import (
    ProposalDocument
)


router = APIRouter(
    prefix="/proposal",
    tags=["Proposal Generator"]
)


def get_proposal_service() -> ProposalGenerationService:

    client = genai.Client(
        api_key=settings.gemini_api_key
    )

    return ProposalGenerationService(
        client=client
    )


def get_pdf_renderer() -> ProposalPdfRenderer:
    return ProposalPdfRenderer()


@router.post(
    "/generate",
    response_model=ProposalContent
)
async def generate_proposal(
    request: ProposalGenerationInput,
    service: ProposalGenerationService = Depends(
        get_proposal_service
    )
):
    return service.generate(request)


@router.post("/pdf")
async def generate_proposal_pdf(
    request: ProposalGenerationInput,
    service: ProposalGenerationService = Depends(
        get_proposal_service
    ),
    renderer: ProposalPdfRenderer = Depends(
        get_pdf_renderer
    )
):

    content = service.generate(request)

    document = ProposalDocument(
        freelancer_name=request.freelancer_name,
        client_name=request.client_name,
        company_name=request.company_name,
        project_type=request.project_type,
        proposal_date=str(date.today()),

        project_overview=content.project_overview,
        scope_of_work=content.scope_of_work,
        deliverables=content.deliverables,
        timeline=content.timeline,
        pricing=content.pricing,
        payment_terms=content.payment_terms,
        assumptions=content.assumptions
    )

    pdf_bytes = renderer.render_pdf(
        document
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=proposal.pdf"
        }
    )