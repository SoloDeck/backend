from typing import Annotated

from fastapi import Depends

from src.ai.contract_generator.chain import ContractGenerator
from src.ai.facade import AIFacade
from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.proposal_generator.chain import ProposalGenerator


def get_ai_facade() -> AIFacade:
    """Dependency provider for AIFacade.
    
    In a more complex setup, these chains might have their own dependencies.
    For now, we instantiate them directly.
    """
    return AIFacade(
        lead_qualifier=LeadQualifier(),
        proposal_generator=ProposalGenerator(),
        contract_generator=ContractGenerator(),
        followup_generator=FollowUpGenerator(),
    )

AIFacadeDep = Annotated[AIFacade, Depends(get_ai_facade)]
