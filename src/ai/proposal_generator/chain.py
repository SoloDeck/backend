import asyncio
from typing import Any

from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.schemas.proposal_generation_input import (
    ProposalGenerationInput,
)


class ProposalGenerator:

    def __init__(self, generation_service: ProposalGenerationService):
        self.generation_service = generation_service

    async def run(
        self,
        *,
        deal_data: dict[str, Any],
        client_data: dict[str, Any],
        user_profile: dict[str, Any],
        template: dict | None = None,
    ) -> dict[str, Any]:

        request = ProposalGenerationInput(
            client_name=client_data.get("name") or "",
            company_name=client_data.get("company_name"),

            project_type=(
                deal_data.get("project_type")
                or deal_data.get("title")
                or ""
            ),

            project_description=deal_data.get("notes")
                                or deal_data.get("description")
                                or "",

            estimated_scope=deal_data.get("estimated_scope"),

            budget=deal_data.get("budget"),

            urgency=deal_data.get("urgency"),

            service_category=deal_data.get("service_category") or "",

            pricing_tier=deal_data.get("pricing_tier") or "",

            freelancer_name=user_profile.get("name") or "",
        )

        content = await asyncio.to_thread(
            self.generation_service.generate,
            request,
        )

        return content.model_dump(mode="json")
