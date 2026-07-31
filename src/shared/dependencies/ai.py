from typing import Annotated

from fastapi import Depends

from src.ai.contract_generator.chain import ContractGenerator
from src.ai.facade import AIFacade
from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.chain import ProposalGenerator
from src.ai.shared.provider_factory import ProviderFactory
from src.shared.dependencies.db import DBSession


async def get_ai_facade(db: DBSession) -> AIFacade:
    # Provider is resolved once per request from the admin-configured
    # ai_provider_configuration row — every chain must use the same one.
    provider = await ProviderFactory(db).get_provider()
    return AIFacade(
        lead_qualifier=LeadQualifier(db),
        proposal_generator=ProposalGenerator(
            generation_service=ProposalGenerationService(provider=provider)
        ),
        contract_generator=ContractGenerator(db),
        followup_generator=FollowUpGenerator(db),
    )


AIFacadeDep = Annotated[AIFacade, Depends(get_ai_facade)]
