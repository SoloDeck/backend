import json
import pytest

from src.ai.lead_qualifier.application.service import LeadQualifierService


# -----------------------------
# MOCKS
# -----------------------------

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


class FakeModels:
    def __init__(self, response):
        self._response = response

    def generate_content(self, *args, **kwargs):
        return self._response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


# -----------------------------
# TESTS
# -----------------------------

def test_qualify_success(monkeypatch):

    monkeypatch.setattr(
        "google.genai.Client",
        lambda *args, **kwargs: FakeClient(MockResponse())
    )

    result = LeadQualifierService.qualify("Need a website")

    assert result["project_type"] == "Website"
    assert result["suggested_lead_score"] == "WARM"


def test_markdown_json_cleaning(monkeypatch):

    monkeypatch.setattr(
        "google.genai.Client",
        lambda *args, **kwargs: FakeClient(MarkdownResponse())
    )

    result = LeadQualifierService.qualify("Need a website")

    assert result["project_type"] == "Website"


def test_invalid_json(monkeypatch):

    monkeypatch.setattr(
        "google.genai.Client",
        lambda *args, **kwargs: FakeClient(InvalidResponse())
    )

    with pytest.raises(json.JSONDecodeError):
        LeadQualifierService.qualify("Need a website")