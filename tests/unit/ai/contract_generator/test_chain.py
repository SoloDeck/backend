"""ContractGenerator.run() ghép đủ ContractContentDTO và không để AI đụng parties."""

import json
from typing import Any

import pytest

from src.ai.contract_generator.chain import ContractGenerator


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.last_kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_kwargs = kwargs
        return _FakeResponse(self._content)


class _FakeGroq:
    def __init__(self, content: str) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content)})()


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


def _run(chain: ContractGenerator, **kwargs: Any) -> dict[str, Any]:
    import asyncio

    return asyncio.run(chain.run(**kwargs))


class TestContractGeneratorRun:
    def test_ghep_du_8_truong_cua_dto(self) -> None:
        chain = ContractGenerator()
        chain.set_client_for_tests(_FakeGroq(VALID_OUTPUT))

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

        chain = ContractGenerator()
        chain.set_client_for_tests(_FakeGroq(model_bia_parties))

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
        chain = ContractGenerator()
        chain.set_client_for_tests(_FakeGroq(VALID_OUTPUT))

        content = _run(chain, client_data={}, user_profile={})

        assert content["governing_law"] == "Vietnam"

    def test_bat_json_mode_khi_goi_groq(self) -> None:
        """Thiếu cờ này là llama-4-scout bọc JSON trong văn bản dẫn nhập -> parser vỡ."""
        fake = _FakeGroq(VALID_OUTPUT)
        chain = ContractGenerator()
        chain.set_client_for_tests(fake)

        _run(chain, client_data={}, user_profile={})

        assert fake.chat.completions.last_kwargs["response_format"] == {"type": "json_object"}

    def test_model_boc_json_trong_van_ban_van_doc_duoc(self) -> None:
        raw = f"Đây là hợp đồng bạn yêu cầu:\n```json\n{VALID_OUTPUT}\n```\nChúc bạn may mắn!"

        chain = ContractGenerator()
        chain.set_client_for_tests(_FakeGroq(raw))

        content = _run(chain, client_data={}, user_profile={})

        assert content["scope_of_work"] == "Thiết kế logo cho quán Cafe."

    def test_model_tra_rac_thi_bao_loi_ro_rang(self) -> None:
        from src.shared.exceptions.domain import AIOutputParseError

        chain = ContractGenerator()
        chain.set_client_for_tests(_FakeGroq("xin lỗi tôi không thể"))

        with pytest.raises(AIOutputParseError):
            _run(chain, client_data={}, user_profile={})
