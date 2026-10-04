"""Mọi nhà cung cấp LLM phải trả số token cùng MỘT dạng cho bên ghi chi phí.

Hai lỗi đã có thật: Ollama trả dataclass trong khi `record_cost` gọi `usage.get(...)` →
AttributeError sau khi model đã trả lời xong; Gemini trả `None` → bảng chi phí AI của
admin trống trơn khi chạy Gemini.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.shared.llm_provider import OllamaProvider
from src.ai.shared.token_usage import extract_gemini_usage, usage_record
from src.modules.subscriptions.application.ai_usage import AiUsageService

USAGE_KEYS = {"model_used", "input_tokens", "output_tokens", "estimated_cost_usd"}


class TestGemini:
    def test_token_ra_gom_ca_phan_suy_nghi(self) -> None:
        response = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=1000, candidates_token_count=200, thoughts_token_count=300
            )
        )

        usage = extract_gemini_usage(response, model="gemini-2.5-flash")

        assert usage["input_tokens"] == 1000
        assert usage["output_tokens"] == 500
        # 1000 × 0,30/1tr + 500 × 2,50/1tr = 0,0003 + 0,00125
        assert usage["estimated_cost_usd"] == Decimal("0.001550")

    def test_model_chua_co_don_gia_van_giu_so_token_chi_phi_0(self) -> None:
        response = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=40, candidates_token_count=10, thoughts_token_count=None
            )
        )

        usage = extract_gemini_usage(response, model="gemini-3.5-flash-lite")

        assert (usage["input_tokens"], usage["output_tokens"]) == (40, 10)
        assert usage["estimated_cost_usd"] == Decimal("0")

    def test_response_thieu_usage_metadata_khong_no(self) -> None:
        usage = extract_gemini_usage(SimpleNamespace(), model="gemini-2.5-flash")
        assert set(usage) == USAGE_KEYS
        assert usage["input_tokens"] == 0


class TestOllama:
    async def test_tra_dict_ma_ben_ghi_chi_phi_doc_duoc(self) -> None:
        http_response = MagicMock()
        http_response.json.return_value = {
            "model": "qwen3:4b",
            "response": "{}",
            "prompt_eval_count": 12,
            "eval_count": 7,
        }
        http_client = AsyncMock()
        http_client.post.return_value = http_response
        http_client.__aenter__.return_value = http_client

        with patch("src.ai.shared.llm_provider.httpx.AsyncClient", return_value=http_client):
            result = await OllamaProvider("qwen3:4b").generate(prompt="x", json_mode=True)

        assert result.usage == usage_record(model="qwen3:4b", input_tokens=12, output_tokens=7)

        db = MagicMock()
        db.flush = AsyncMock()
        await AiUsageService(db=db).record_cost(
            uuid.uuid4(), ai_module="lead_qualifier", usage=result.usage
        )
        written = db.add.call_args.args[0]
        assert (written.input_tokens, written.output_tokens) == (12, 7)


@pytest.mark.parametrize(
    "price_in,price_out", [(Decimal(0), Decimal(0)), (Decimal("1"), Decimal("2"))]
)
def test_usage_record_luon_du_bon_truong(price_in: Decimal, price_out: Decimal) -> None:
    usage = usage_record(
        model="m", input_tokens=1, output_tokens=1, price_in=price_in, price_out=price_out
    )
    assert set(usage) == USAGE_KEYS
