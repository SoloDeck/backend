from src.ai.proposal_generator.application.service import ProposalGenerationService


def test_clean_response_removes_json_fences():
    service = ProposalGenerationService(client=None)

    raw = """```json
{"a": 1}
```"""

    cleaned = service._clean_response(raw)

    assert cleaned == '{"a": 1}'

from unittest.mock import Mock

from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.schemas.ProposalGenerationInput import ProposalGenerationInput


class FakeResponse:
    text = """
    {
        "project_overview": "Website redesign",
        "scope_of_work": ["UI", "UX"],
        "deliverables": ["Homepage"],
        "timeline": "2 weeks",
        "pricing": "$1000",
        "payment_terms": "50% upfront",
        "assumptions": ["Client provides assets"]
    }
    """


def test_generate_success():
    fake_client = Mock()
    fake_client.models.generate_content.return_value = FakeResponse()

    service = ProposalGenerationService(fake_client)

    request = ProposalGenerationInput(
        client_name="Acme",
        company_name="Acme Inc",
        project_type="Website",
        project_description="Redesign site",
        estimated_scope=None,
        budget="$1000",
        urgency=None,
        service_category="Web",
        pricing_tier="Standard",
        freelancer_name="John",
    )

    result = service.generate(request)

    assert result.project_overview == "Website redesign"
    assert result.scope_of_work == ["UI", "UX"]
    assert result.assumptions == ["Client provides assets"]

    fake_client.models.generate_content.assert_called_once()

import pytest
from unittest.mock import Mock

from src.ai.proposal_generator.application.service import ProposalGenerationService
from src.ai.proposal_generator.schemas.ProposalGenerationInput import ProposalGenerationInput


class FakeResponse:
    text = "NOT JSON"


def test_generate_invalid_json_raises():
    fake_client = Mock()
    fake_client.models.generate_content.return_value = FakeResponse()

    service = ProposalGenerationService(fake_client)

    request = ProposalGenerationInput(
        client_name="Acme",
        company_name=None,
        project_type="Website",
        project_description="Redesign",
        estimated_scope=None,
        budget=None,
        urgency=None,
        service_category="Web",
        pricing_tier="Standard",
        freelancer_name="John",
    )

    with pytest.raises(ValueError):
        service.generate(request)

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