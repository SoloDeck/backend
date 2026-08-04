"""FollowUpGenerator soạn được tin nhắn, và chịu được đầu ra lởm của model."""

import asyncio
import json
from typing import Any

import pytest

from src.ai.followup_generator.chain import FollowUpGenerator
from src.ai.shared.llm_provider import LLMResponse
from src.shared.exceptions.domain import AIOutputParseError


class FakeProvider:
    """Stands in for a real BaseLLMProvider (Groq/Gemini/...) — no network calls."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict[str, Any] = {}

    async def generate(self, **kwargs: Any) -> LLMResponse:
        self.last_kwargs = kwargs
        return LLMResponse(text=self._text)


VALID = json.dumps(
    {
        "subject": "Nhắc thanh toán hoá đơn INV-001",
        "message_text": "Chào anh Mười, em nhắc anh hoá đơn INV-001 đã tới hạn ạ.",
    },
    ensure_ascii=False,
)


def _make_chain(text: str) -> FollowUpGenerator:
    chain = FollowUpGenerator(db=None)
    chain._provider = FakeProvider(text)
    return chain


def _run(chain: FollowUpGenerator, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(chain.run(**kwargs))


class TestFollowUpGenerator:
    def test_soan_duoc_tin_nhan(self) -> None:
        chain = _make_chain(VALID)

        result = _run(
            chain,
            reminder_type="payment_due",
            deal_data={"số hoá đơn": "INV-001"},
            client_data={"name": "Nguyễn Văn Mười"},
        )

        assert result["message_text"].startswith("Chào anh Mười")
        assert result["subject"] == "Nhắc thanh toán hoá đơn INV-001"

    def test_ep_mang_thanh_chuoi(self) -> None:
        """llama-4-scout hay trả mảng gạch đầu dòng dù prompt yêu cầu một đoạn văn."""
        raw = json.dumps(
            {"subject": "", "message_text": ["Chào anh Mười,", "Em nhắc anh hoá đơn ạ."]},
            ensure_ascii=False,
        )
        chain = _make_chain(raw)

        result = _run(chain, reminder_type="follow_up", client_data={})

        assert result["message_text"] == "Chào anh Mười,\nEm nhắc anh hoá đơn ạ."

    def test_thieu_subject_thi_de_rong(self) -> None:
        raw = json.dumps({"message_text": "Chào anh ạ."}, ensure_ascii=False)
        chain = _make_chain(raw)

        assert _run(chain, reminder_type="follow_up")["subject"] == ""

    def test_bat_json_mode_khi_goi_groq(self) -> None:
        """Thiếu cờ này là llama-4-scout bọc JSON trong văn bản dẫn nhập -> parser vỡ."""
        chain = _make_chain(VALID)

        _run(chain, reminder_type="follow_up")

        assert chain._provider.last_kwargs["json_mode"] is True

    def test_model_boc_json_trong_van_ban_van_doc_duoc(self) -> None:
        raw = f"Đây là tin nhắn bạn cần:\n```json\n{VALID}\n```\nChúc may mắn!"
        chain = _make_chain(raw)

        assert "Chào anh Mười" in _run(chain, reminder_type="follow_up")["message_text"]

    def test_model_tra_rac_thi_bao_loi_ro_rang(self) -> None:
        chain = _make_chain("xin lỗi tôi không thể")

        with pytest.raises(AIOutputParseError):
            _run(chain, reminder_type="follow_up")
