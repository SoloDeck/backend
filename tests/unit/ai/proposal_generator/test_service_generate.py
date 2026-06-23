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