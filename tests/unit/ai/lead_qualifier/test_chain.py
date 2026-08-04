import json
from typing import Any

import pytest

from src.ai.lead_qualifier.chain import LeadQualifier
from src.ai.shared.llm_provider import LLMResponse
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


class FakeProvider:
    """Stands in for a real BaseLLMProvider (Groq/Gemini/...) — no network calls."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict[str, Any] = {}

    async def generate(self, **kwargs: Any) -> LLMResponse:
        self.last_kwargs = kwargs
        return LLMResponse(text=self._text)


def _make_qualifier(data: dict) -> LeadQualifier:
    q = LeadQualifier(db=None)
    q._provider = FakeProvider(json.dumps(data))
    return q


# --------------------------------------------------
# _parse_output
# --------------------------------------------------


class TestParseOutput:
    def test_plain_json(self):
        q = LeadQualifier(db=None)
        assert q._parse_output('{"project_type": "Website"}') == {"project_type": "Website"}

    def test_markdown_fenced_json(self):
        q = LeadQualifier(db=None)
        raw = '```json\n{"project_type": "Website"}\n```'
        assert q._parse_output(raw) == {"project_type": "Website"}

    def test_preamble_before_fenced_json(self):
        """Đúng chuỗi đã làm hỏng production: câu dẫn, rồi fence không nhãn.

        llama-4-scout cứ thêm câu dẫn ở đầu. Parser cũ chỉ cắt fence khi câu trả lời
        BẮT ĐẦU bằng fence, nên ca này ném AIOutputParseError và kết quả AI hoàn toàn
        đúng bị vứt đi.  #Huynh
        """
        q = LeadQualifier(db=None)
        raw = (
            "Here is the draft qualification result:\n\n"
            "```\n"
            '{"project_type": "E-commerce Website", "suggested_lead_score": "HOT"}\n'
            "```"
        )
        assert q._parse_output(raw) == {
            "project_type": "E-commerce Website",
            "suggested_lead_score": "HOT",
        }

    def test_preamble_without_fence(self):
        q = LeadQualifier(db=None)
        raw = 'Sure! Here you go: {"project_type": "Website"}'
        assert q._parse_output(raw) == {"project_type": "Website"}

    def test_trailing_commentary_after_json(self):
        q = LeadQualifier(db=None)
        raw = '{"project_type": "Website"}\n\nLet me know if you need anything else!'
        assert q._parse_output(raw) == {"project_type": "Website"}

    def test_nested_objects_are_not_truncated(self):
        """Greedy quan trọng ở đây: non-greedy sẽ dừng ở dấu `}` đầu tiên.  #Huynh"""
        q = LeadQualifier(db=None)
        raw = (
            "Result:\n"
            '{"detected_signals": [{"text": "Clear budget", "is_positive": true}], '
            '"price_range_min": 40000000}'
        )
        assert q._parse_output(raw) == {
            "detected_signals": [{"text": "Clear budget", "is_positive": True}],
            "price_range_min": 40000000,
        }

    def test_malformed_raises(self):
        q = LeadQualifier(db=None)
        with pytest.raises(AIOutputParseError):
            q._parse_output("not valid json")

    def test_prose_with_broken_json_still_raises(self):
        """Có khối `{...}` nhưng JSON hỏng thì VẪN phải báo lỗi, không nuốt im lặng.  #Huynh"""
        q = LeadQualifier(db=None)
        with pytest.raises(AIOutputParseError):
            q._parse_output("Here you go: {project_type: Website,,}")

    def test_empty_string_raises(self):
        q = LeadQualifier(db=None)
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

    async def test_missing_inquiry_text_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_text is required"):
            await q.run()

    async def test_empty_inquiry_text_raises(self):
        q = _make_qualifier(VALID_MOCK_DATA)
        with pytest.raises(ValueError, match="inquiry_text is required"):
            await q.run(inquiry_text="")

    async def test_markdown_response_cleaned(self):
        raw_md = f"```json\n{json.dumps(VALID_MOCK_DATA)}\n```"
        q = LeadQualifier(db=None)
        q._provider = FakeProvider(raw_md)
        result = await q.run(inquiry_text="Need a website")
        assert result["suggested_lead_score"] == "HOT"

    async def test_invalid_json_from_model_raises(self):
        q = LeadQualifier(db=None)
        q._provider = FakeProvider("not json")
        with pytest.raises(AIOutputParseError):
            await q.run(inquiry_text="Need a website")

    async def test_red_flags_populated(self):
        data = {**VALID_MOCK_DATA, "red_flags": ["No clear scope", "Unrealistic deadline"]}
        q = _make_qualifier(data)
        result = await q.run(inquiry_text="Need a website")
        assert len(result["red_flags"]) == 2

    async def test_json_mode_requested_from_provider(self):
        """json_mode=True is what keeps llama-4-scout from wrapping JSON in prose."""
        q = _make_qualifier(VALID_MOCK_DATA)
        await q.run(inquiry_text="Need a website")
        assert q._provider.last_kwargs["json_mode"] is True
