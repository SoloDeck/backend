from typing import Annotated

from fastapi import Depends
from google import genai

from src.ai.contract_generator.chain import ContractGenerator
from src.ai.facade import AIFacade
from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.chain import ProposalGenerator
from src.config.settings import settings


def get_ai_facade() -> AIFacade:
    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return AIFacade(
        lead_qualifier=LeadQualifier(),
        proposal_generator=ProposalGenerator(
            generation_service=ProposalGenerationService(client=gemini_client)
        ),
        contract_generator=ContractGenerator(),
        followup_generator=FollowUpGenerator(),
    )


AIFacadeDep = Annotated[AIFacade, Depends(get_ai_facade)]
