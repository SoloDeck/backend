import pytest
from unittest.mock import Mock

from src.ai.proposal_generator.chain import ProposalGenerator
from src.ai.proposal_generator.schemas.ProposalContent import ProposalContent


@pytest.mark.asyncio
async def test_chain_maps_inputs_correctly():

    fake_service = Mock()

    fake_service.generate.return_value = ProposalContent(
        project_overview="Overview",
        scope_of_work=["A"],
        deliverables=["B"],
        timeline="1 week",
        pricing="$100",
        payment_terms="50%",
        assumptions=["A1"],
    )

    chain = ProposalGenerator(fake_service)

    result = await chain.run(
        deal_data={
            "project_type": "Website",
            "notes": "Build landing page",
            "budget": "$100",
            "service_category": "Web",
            "pricing_tier": "Basic",
        },
        client_data={
            "name": "Acme",
            "company_name": "Acme Inc",
        },
        user_profile={
            "name": "John",
        },
        template=None,
    )

    fake_service.generate.assert_called_once()

    request = fake_service.generate.call_args.args[0]

    assert request.client_name == "Acme"
    assert request.project_type == "Website"
    assert request.project_description == "Build landing page"
    assert request.freelancer_name == "John"

    assert result["project_overview"] == "Overview"