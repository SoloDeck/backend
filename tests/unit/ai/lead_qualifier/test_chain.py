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


@pytest.fixture(autouse=True)
def _stub_retriever(monkeypatch):
    """Keep unit tests offline.

    `run()` now lazily builds the Gemini-backed FAISS retriever, which would
    hit the Google embeddings API (needs GEMINI_API_KEY + network). Seed the
    cached `_retriever` with a no-op stub so `_get_retriever()` never builds
    the real one.
    """

    class _FakeRetriever:
        def retrieve(self, *, profession, query):
            return ""

    monkeypatch.setattr(LeadQualifier, "_retriever", _FakeRetriever())


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

    async def test_run_feeds_retrieved_knowledge_into_prompt(self, monkeypatch):
        """The knowledge returned by the retriever must reach the LLM prompt.

        Overrides the autouse stub with a retriever that emits a recognizable
        sentinel, then captures the prompt handed to the Groq call path and
        asserts the sentinel is embedded in it.
        """

        class _SentinelRetriever:
            def __init__(self):
                self.calls = []

            def retrieve(self, *, profession, query):
                self.calls.append((profession, query))
                return "SENTINEL-KNOWLEDGE-BLOCK"

        sentinel_retriever = _SentinelRetriever()
        monkeypatch.setattr(LeadQualifier, "_retriever", sentinel_retriever)

        q = _make_qualifier(VALID_MOCK_DATA)

        captured = {}

        def _capture(prompt):
            captured["prompt"] = prompt
            return json.dumps(VALID_MOCK_DATA)

        monkeypatch.setattr(q, "_call_groq", _capture)

        result = await q.run(
            profession="software-developer",
            inquiry_context="Need a website",
        )

        assert result["suggested_lead_score"] == "HOT"
        # Retriever was consulted with the caller's profession + inquiry.
        assert sentinel_retriever.calls == [("software-developer", "Need a website")]
        # Retrieved knowledge was threaded through the prompt builder into the LLM call.
        assert "SENTINEL-KNOWLEDGE-BLOCK" in captured["prompt"]
