from typing import Annotated

from fastapi import Depends
from groq import Groq

from src.ai.contract_generator.chain import ContractGenerator
from src.ai.facade import AIFacade
from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.chain import ProposalGenerator
from src.config.settings import settings


def get_ai_facade() -> AIFacade:
    # Trước đây dựng genai.Client (Gemini) rồi đưa vào ProposalGenerationService,
    # trong khi service gọi client.chat.completions.create — cú pháp của Groq. Gemini
    # client không có .chat nên ném AttributeError. Đây là cùng một bug với
    # modules/proposals/api/router.py; worker Celery lấy facade từ đây nên job
    # proposal_generator cũng chết theo.  #Huynh
    groq_client = Groq(api_key=settings.groq_api_key)
    return AIFacade(
        lead_qualifier=LeadQualifier(),
        proposal_generator=ProposalGenerator(
            generation_service=ProposalGenerationService(client=groq_client)
        ),
        contract_generator=ContractGenerator(),
        followup_generator=FollowUpGenerator(),
    )


AIFacadeDep = Annotated[AIFacade, Depends(get_ai_facade)]
