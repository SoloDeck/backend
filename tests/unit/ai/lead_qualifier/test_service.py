import json

import pytest

from src.ai.lead_qualifier.application.service import (
    LeadQualifierService
)


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
# TEST SUCCESSFUL QUALIFICATION
# --------------------------------------------------

def test_qualify_success(monkeypatch):

    captured = {}

    def mock_generate_content(*args, **kwargs):
        captured.update(kwargs)
        return MockResponse()

    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client.models.generate_content",
        mock_generate_content
    )

    result = LeadQualifierService.qualify(
        "Need a website"
    )

    assert result == {
        "project_type": "Website",
        "budget_signal": "20 million",
        "timeline_signal": "1 month",
        "urgency_signal": "Medium",
        "red_flags": [],
        "suggested_lead_score": "WARM",
        "reasoning": "Test",
    }

    assert captured["model"] == "gemini-2.5-flash"
    assert "Need a website" in captured["contents"]


# --------------------------------------------------
# TEST MARKDOWN JSON CLEANING
# --------------------------------------------------

def test_markdown_json_cleaning(monkeypatch):

    def mock_generate_content(*args, **kwargs):
        return MarkdownResponse()

    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client.models.generate_content",
        mock_generate_content
    )

    result = LeadQualifierService.qualify(
        "Need a website"
    )

    assert result["project_type"] == "Website"
    assert result["suggested_lead_score"] == "WARM"


# --------------------------------------------------
# TEST INVALID JSON RESPONSE
# --------------------------------------------------

def test_invalid_json(monkeypatch):

    def mock_generate_content(*args, **kwargs):
        return InvalidResponse()

    monkeypatch.setattr(
        "src.ai.lead_qualifier.application.service.client.models.generate_content",
        mock_generate_content
    )

    with pytest.raises(json.JSONDecodeError):
        LeadQualifierService.qualify(
            "Need a website"
        )