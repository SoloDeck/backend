import json
import pytest

from src.ai.lead_qualifier.application.service import LeadQualifierService


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
# MOCK RESPONSES
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


# --------------------------------------------------
# FIX: safe fake client replacement
# --------------------------------------------------

class FakeModels:
    def __init__(self, response):
        self._response = response

    def generate_content(self, *args, **kwargs):
        return self._response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


# --------------------------------------------------
# TEST SUCCESSFUL QUALIFICATION
# --------------------------------------------------

def test_qualify_success(monkeypatch):

    captured = {}

    fake_client = FakeClient(MockResponse())

    def mock_client(*args, **kwargs):
        return fake_client

    # patch the actual module-level client used in service.py
    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client",
        fake_client
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
# TEST MARKDOWN JSON CLEANING
# --------------------------------------------------

def test_markdown_json_cleaning(monkeypatch):

    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client",
        FakeClient(MarkdownResponse())
    )

    result = LeadQualifierService.qualify("Need a website")

    assert result["project_type"] == "Website"
    assert result["suggested_lead_score"] == "WARM"


# --------------------------------------------------
# TEST INVALID JSON RESPONSE
# --------------------------------------------------

def test_invalid_json(monkeypatch):

    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client",
        FakeClient(InvalidResponse())
    )

    with pytest.raises(json.JSONDecodeError):
        LeadQualifierService.qualify("Need a website")