import json

import pytest

from src.ai.lead_qualifier.chain import LeadQualifier
from src.shared.exceptions.domain import AIOutputParseError

# --------------------------------------------------
# FIXTURES / MOCKS
# --------------------------------------------------

VALID_MOCK_DATA = {
    "project_type": "E-commerce website",
    "budget_signal": "50-80 million VND",
    "timeline_signal": "3 months",
    "urgency_signal": "Medium",
    "red_flags": [],
    "suggested_lead_score": "HOT",
    "reasoning": "Clear budget and timeline provided.",
}


class MockResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, response):
        self._response = response

    async def generate_content(self, *args, **kwargs):
        return self._response


class FakeAio:
    def __init__(self, response):
        self.models = FakeModel(response)


class FakeClient:
    def __init__(self, response):
        self.models = FakeModel(response)
        self.aio = FakeAio(response)


def _make_qualifier(data: dict) -> LeadQualifier:
    q = LeadQualifier()
    q.set_client_for_tests(FakeClient(MockResponse(json.dumps(data))))
    return q


# --------------------------------------------------
# _get_client
# --------------------------------------------------


class TestGetClient:
    def test_missing_api_key_raises(self, monkeypatch):
        from src.config.settings import settings
        monkeypatch.setattr(settings, "gemini_api_key", "")
        q = LeadQualifier()
        # Clear existing cached client if any
        q._client = None
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set in settings"):
            q._get_client()

    def test_success_returns_client(self, monkeypatch):
        from src.config.settings import settings
        monkeypatch.setattr(settings, "gemini_api_key", "fake-key")
        q = LeadQualifier()
        # Clear existing cached client if any
        q._client = None
        client = q._get_client()
        assert client is not None


# --------------------------------------------------
# _parse_output
# --------------------------------------------------


class TestParseOutput:
    def test_plain_json(self):
        q = LeadQualifier()
        assert q._parse_output('{"project_type": "Website"}') == {"project_type": "Website"}

    def test_markdown_fenced_json(self):
        q = LeadQualifier()
        raw = "```json\n{\"project_type\": \"Website\"}\n```"
        assert q._parse_output(raw) == {"project_type": "Website"}

    def test_malformed_raises(self):
        q = LeadQualifier()
        with pytest.raises(AIOutputParseError):
            q._parse_output("not valid json")

    def test_empty_string_raises(self):
        q = LeadQualifier()
        with pytest.raises(AIOutputParseError):
            q._parse_output("")


# --------------------------------------------------
# run()
# --------------------------------------------------


class TestRun:
    async def test_success_returns_dict(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        result = await q.run(inquiry_text="Need a website")
        assert result["project_type"] == "E-commerce website"
        assert result["suggested_lead_score"] == "HOT"

    async def test_all_fields_present(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        result = await q.run(inquiry_text="Need a website")
        for field in ("project_type", "budget_signal", "timeline_signal",
                      "urgency_signal", "red_flags", "suggested_lead_score", "reasoning"):
            assert field in result

    async def test_missing_inquiry_text_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_text is required"):
            await q.run()

    async def test_empty_inquiry_text_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_text is required"):
            await q.run(inquiry_text="")

    async def test_markdown_response_cleaned(self):
        q = LeadQualifier()
        raw_md = f"```json\n{json.dumps(VALID_MOCK_DATA)}\n```"
        q.set_client_for_tests(FakeClient(MockResponse(raw_md)))
        result = await q.run(inquiry_text="Need a website")
        assert result["suggested_lead_score"] == "HOT"

    async def test_invalid_json_from_model_raises(self):
        q = LeadQualifier()
        q.set_client_for_tests(FakeClient(MockResponse("not json")))
        with pytest.raises(AIOutputParseError):
            await q.run(inquiry_text="Need a website")

    async def test_red_flags_populated(self):
        data = {**VALID_MOCK_DATA, "red_flags": ["No clear scope", "Unrealistic deadline"]}
        q = _make_qualifier(data)
        result = await q.run(inquiry_text="Need a website")
        assert len(result["red_flags"]) == 2
