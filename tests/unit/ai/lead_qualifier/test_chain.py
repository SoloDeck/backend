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


class MockMessage:
    def __init__(self, content):
        self.content = content


class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)


class MockCompletion:
    def __init__(self, content):
        self.choices = [MockChoice(content)]


class MockCompletions:
    def __init__(self, content):
        self._content = content

    def create(self, *args, **kwargs):
        return MockCompletion(self._content)


class MockChat:
    def __init__(self, content):
        self.completions = MockCompletions(content)


class FakeClient:
    """Mimics the shape of a Groq client's `client.chat.completions.create(...)`."""

    def __init__(self, content):
        self.chat = MockChat(content)


def _make_qualifier(data: dict) -> LeadQualifier:
    q = LeadQualifier()
    q.set_client_for_tests(FakeClient(json.dumps(data)))
    return q


# --------------------------------------------------
# _get_client
# --------------------------------------------------


class TestGetClient:
    def test_missing_api_key_raises(self, monkeypatch):
        from src.config.settings import settings

        monkeypatch.setattr(settings, "groq_api_key", "")
        q = LeadQualifier()
        # Clear existing cached client if any
        q._client = None
        with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
            q._get_client()

    def test_success_returns_client(self, monkeypatch):
        from src.config.settings import settings

        monkeypatch.setattr(settings, "groq_api_key", "fake-key")
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
        raw = '```json\n{"project_type": "Website"}\n```'
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
        result = await q.run(profession="software-developer", inquiry_context="Need a website")
        assert result["project_type"] == "E-commerce website"
        assert result["suggested_lead_score"] == "HOT"

    async def test_all_fields_present(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        result = await q.run(profession="software-developer", inquiry_context="Need a website")
        for field in (
            "project_type",
            "budget_signal",
            "timeline_signal",
            "urgency_signal",
            "red_flags",
            "suggested_lead_score",
            "reasoning",
        ):
            assert field in result

    async def test_missing_inquiry_context_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_context is required"):
            await q.run(profession=None, inquiry_context="")

    async def test_empty_inquiry_context_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_context is required"):
            await q.run(profession=None, inquiry_context="")

    async def test_markdown_response_cleaned(self):
        q = LeadQualifier()
        raw_md = f"```json\n{json.dumps(VALID_MOCK_DATA)}\n```"
        q.set_client_for_tests(FakeClient(raw_md))
        result = await q.run(profession="software-developer", inquiry_context="Need a website")
        assert result["suggested_lead_score"] == "HOT"

    async def test_invalid_json_from_model_raises(self):
        q = LeadQualifier()
        q.set_client_for_tests(FakeClient("not json"))
        with pytest.raises(AIOutputParseError):
            await q.run(profession="software-developer", inquiry_context="Need a website")

    async def test_red_flags_populated(self):
        data = {**VALID_MOCK_DATA, "red_flags": ["No clear scope", "Unrealistic deadline"]}
        q = _make_qualifier(data)
        result = await q.run(profession="software-developer", inquiry_context="Need a website")
        assert len(result["red_flags"]) == 2
