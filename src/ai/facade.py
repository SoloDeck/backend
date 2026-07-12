"""AIFacade — single public interface for all AI generation capabilities.

Business modules call AIFacade methods exclusively.
LangChain chains are never instantiated directly from business code.

Dependency graph:
    DealService → AIFacade → LeadQualifier
    DealService → AIFacade → ProposalGenerator
    ContractService → AIFacade → ContractGenerator
    ReminderService → AIFacade → FollowUpGenerator
"""

from dataclasses import dataclass
from typing import Any

import structlog

from src.ai.contract_generator.chain import ContractGenerator
from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.proposal_generator.chain import ProposalGenerator
from src.shared.exceptions.domain import EntitlementError

log = structlog.get_logger()


@dataclass
class AIFacade:
    """Orchestrates AI module access with entitlement enforcement."""

    lead_qualifier: LeadQualifier
    proposal_generator: ProposalGenerator
    contract_generator: ContractGenerator
    followup_generator: FollowUpGenerator

    def _check_entitlement(self, user_can_use_ai: bool) -> None:
        if not user_can_use_ai:
            raise EntitlementError(
                "Your plan does not include AI features. Upgrade to Pro.",
                entitlement="can_use_ai",
            )

    async def qualify_lead(
        self,
        *,
        inquiry_text: str,
        profession: str | None,
        user_can_use_ai: bool,
    ) -> dict[str, Any]:
        self._check_entitlement(user_can_use_ai)

        return await self.lead_qualifier.run(profession=profession,
                                             inquiry_text=inquiry_text)

    async def generate_proposal(
        self,
        *,
        deal_data: dict[str, Any],
        client_data: dict[str, Any],
        user_profile: dict[str, Any],
        template: dict[str, Any] | None,
        user_can_use_ai: bool,
    ) -> dict[str, Any]:
        self._check_entitlement(user_can_use_ai)
        return await self.proposal_generator.run(
            deal_data=deal_data,
            client_data=client_data,
            user_profile=user_profile,
            template=template,
        )

    async def generate_contract(
        self,
        *,
        deal_data: dict[str, Any],
        proposal_content: dict[str, Any],
        client_data: dict[str, Any],
        user_profile: dict[str, Any],
        user_can_use_ai: bool,
    ) -> dict[str, Any]:
        self._check_entitlement(user_can_use_ai)
        return await self.contract_generator.run(
            deal_data=deal_data,
            proposal_content=proposal_content,
            client_data=client_data,
            user_profile=user_profile,
        )

    async def generate_followup(
        self,
        *,
        deal_data: dict[str, Any],
        client_data: dict[str, Any],
        communication_history: list[dict[str, Any]],
        reminder_type: str,
        user_can_use_ai: bool,
    ) -> dict[str, Any]:
        self._check_entitlement(user_can_use_ai)
        return await self.followup_generator.run(
            deal_data=deal_data,
            client_data=client_data,
            communication_history=communication_history,
            reminder_type=reminder_type,
        )
