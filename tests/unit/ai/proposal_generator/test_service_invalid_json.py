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