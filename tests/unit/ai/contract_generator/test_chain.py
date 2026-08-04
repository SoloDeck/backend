"""ContractGenerator.run() ghép đủ ContractContentDTO và không để AI đụng parties."""

import asyncio
import json
from typing import Any

import pytest

from src.ai.contract_generator.chain import ContractGenerator
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


VALID_OUTPUT = json.dumps(
    {
        "scope_of_work": "Thiết kế logo cho quán Cafe.",
        "payment_terms": "Thanh toán 100% trước khi bắt đầu.",
        "revision_policy": "2 lần chỉnh sửa miễn phí.",
        "ip_ownership": "Chuyển giao sau khi thanh toán đủ.",
        "termination_clause": "Báo trước 7 ngày bằng văn bản.",
        "custom_clauses": "",
    },
    ensure_ascii=False,
)


def _make_chain(text: str) -> ContractGenerator:
    chain = ContractGenerator(db=None)
    chain._provider = FakeProvider(text)
    return chain


def _run(chain: ContractGenerator, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(chain.run(**kwargs))


class TestContractGeneratorRun:
    def test_ghep_du_8_truong_cua_dto(self) -> None:
        chain = _make_chain(VALID_OUTPUT)

        content = _run(
            chain,
            deal_data={"title": "design logo cho quán Cafe"},
            proposal_content={"pricing": "700.000 đ"},
            client_data={"name": "Nguyễn Văn Mười", "email": "ngvan10@gmail.com"},
            user_profile={"name": "Huỳnh Hoa", "email": "hoa@example.com"},
        )

        assert set(content) == {
            "parties",
            "scope_of_work",
            "payment_terms",
            "revision_policy",
            "ip_ownership",
            "termination_clause",
            "governing_law",
            "custom_clauses",
        }

    def test_parties_lay_tu_db_khong_phai_tu_ai(self) -> None:
        """Model có bịa parties thì cũng bị code ghi đè."""
        model_bia_parties = json.dumps(
            {
                "scope_of_work": "Thiết kế logo.",
                "payment_terms": "Thanh toán 100% trước.",
                "revision_policy": "2 lần sửa.",
                "ip_ownership": "Chuyển giao.",
                "termination_clause": "Báo trước 7 ngày.",
                "parties": {"client": {"name": "Trần Văn Bịa", "email": "bia@fake.com"}},
            },
            ensure_ascii=False,
        )

        chain = _make_chain(model_bia_parties)

        content = _run(
            chain,
            deal_data={},
            proposal_content={},
            client_data={"name": "Nguyễn Văn Mười", "email": "ngvan10@gmail.com"},
            user_profile={"name": "Huỳnh Hoa", "email": "hoa@example.com"},
        )

        assert content["parties"]["client"]["name"] == "Nguyễn Văn Mười"
        assert content["parties"]["client"]["email"] == "ngvan10@gmail.com"

    def test_governing_law_luon_la_vietnam(self) -> None:
        chain = _make_chain(VALID_OUTPUT)

        content = _run(chain, client_data={}, user_profile={})

        assert content["governing_law"] == "Vietnam"

    def test_bat_json_mode_khi_goi_groq(self) -> None:
        """Thiếu cờ này là llama-4-scout bọc JSON trong văn bản dẫn nhập -> parser vỡ."""
        chain = _make_chain(VALID_OUTPUT)

        _run(chain, client_data={}, user_profile={})

        assert chain._provider.last_kwargs["json_mode"] is True

    def test_model_boc_json_trong_van_ban_van_doc_duoc(self) -> None:
        raw = f"Đây là hợp đồng bạn yêu cầu:\n```json\n{VALID_OUTPUT}\n```\nChúc bạn may mắn!"

        chain = _make_chain(raw)

        content = _run(chain, client_data={}, user_profile={})

        assert content["scope_of_work"] == "Thiết kế logo cho quán Cafe."

    def test_model_tra_rac_thi_bao_loi_ro_rang(self) -> None:
        chain = _make_chain("xin lỗi tôi không thể")

        with pytest.raises(AIOutputParseError):
            _run(chain, client_data={}, user_profile={})
