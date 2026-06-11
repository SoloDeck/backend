import json
import pytest

from src.ai.lead_qualifier.application.service import LeadQualifierService


# --------------------------------------------------
# FIXTURES / MOCKS
# --------------------------------------------------

class MockResponse:
    text = """
    {
        "project_type": "Website",
        "budget_signal": "20 million",
        "timeline_signal": "1 month",
        "urgency_signal": "Medium",
        "red_flags": [],
        "suggested_lead_score": "WARM",
        "reasoning": "Test"
    }
    """


class MarkdownResponse:
    text = """
    ```json
    {
        "project_type": "Website",
        "budget_signal": "20 million",
        "timeline_signal": "1 month",
        "urgency_signal": "Medium",
        "red_flags": [],
        "suggested_lead_score": "WARM",
        "reasoning": "Test"
    }
    ```
    """


class InvalidResponse:
    text = "This is not JSON"


class FakeModel:
    def __init__(self, response):
        self._response = response

    def generate_content(self, *args, **kwargs):
        return self._response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModel(response)


# --------------------------------------------------
# TEST CLEAN JSON RESPONSE
# --------------------------------------------------

def test_clean_json_response():
    raw = """
    ```json
    {
        "project_type": "Website"
    }
    ```
    """

    cleaned = LeadQualifierService.clean_json_response(raw)

    assert cleaned == """
    {
        "project_type": "Website"
    }
    """.strip()


# --------------------------------------------------
# TEST SUCCESSFUL QUALIFICATION
# --------------------------------------------------

def test_qualify_success():
    LeadQualifierService.set_client_for_tests(
        FakeClient(MockResponse())
    )

    result = LeadQualifierService.qualify("Need a website")

    assert result == {
        "project_type": "Website",
        "budget_signal": "20 million",
        "timeline_signal": "1 month",
        "urgency_signal": "Medium",
        "red_flags": [],
        "suggested_lead_score": "WARM",
        "reasoning": "Test",
    }


# --------------------------------------------------
# TEST MARKDOWN CLEANING PATH
# --------------------------------------------------

def test_markdown_json_cleaning():
    LeadQualifierService.set_client_for_tests(
        FakeClient(MarkdownResponse())
    )

    result = LeadQualifierService.qualify("Need a website")

    assert result["project_type"] == "Website"
    assert result["suggested_lead_score"] == "WARM"


# --------------------------------------------------
# TEST INVALID JSON HANDLING
# --------------------------------------------------

def test_invalid_json():
    LeadQualifierService.set_client_for_tests(
        FakeClient(InvalidResponse())
    )

    with pytest.raises(json.JSONDecodeError):
        LeadQualifierService.qualify("Need a website")