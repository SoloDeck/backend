"""Danh sách nhà cung cấp LLM phải nhất quán giữa các nơi dùng nó.

Trước đây danh sách được viết tay ở ba chỗ (Literal của schema admin, set
SUPPORTED_LLM_PROVIDERS, chuỗi if/elif trong get_llm_provider). Giờ tất cả suy
ra từ LLMProviderName; các test dưới đây canh để chúng không lệch nhau lần nữa.
"""

from typing import get_args

import pytest

from src.ai.shared.constants import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    SUPPORTED_LLM_MODELS,
    SUPPORTED_LLM_PROVIDERS,
    LLMProviderName,
)
from src.ai.shared.llm_provider import _PROVIDERS, BaseLLMProvider, get_llm_provider
from src.shared.exceptions.domain import AIGenerationError
from src.config.settings import settings
from src.modules.admin.schemas.request import AdminUpdateLLMProviderRequest


@pytest.fixture(autouse=True)
def _provider_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cấp key giả cho mọi nhà cung cấp.

    Provider đọc API key ngay trong __init__ và ném RuntimeError nếu trống, nên
    nếu không ghim thì các test dựng provider dưới đây sẽ xanh ở máy dev (có
    `.env`) và đỏ trên CI — job test KHÔNG đặt GROQ_API_KEY/GEMINI_API_KEY.
    """
    # Chỉ nhà cung cấp NÀO có trường khoá mới ghim: Settings là pydantic model nên
    # gán một tên lạ (vd `ollama_api_key`) là lỗi, `raising=False` của monkeypatch
    # không đỡ được vì lỗi đến từ `__setattr__` của pydantic. Ollama xác thực bằng
    # `ollama_base_url` chứ không có khoá.
    for name in SUPPORTED_LLM_PROVIDERS:
        field = f"{name}_api_key"
        if field in type(settings).model_fields:
            monkeypatch.setattr(settings, field, f"test-{name}-key")


class TestProviderRegistryConsistency:
    def test_supported_set_matches_the_literal(self) -> None:
        assert frozenset(get_args(LLMProviderName)) == SUPPORTED_LLM_PROVIDERS

    def test_every_supported_provider_is_constructible(self) -> None:
        """Thêm nhà cung cấp vào Literal mà quên map trong _PROVIDERS -> fail ở đây.

        Nếu không có test này, sai sót chỉ lộ ra khi admin đổi sang nhà cung cấp
        đó và MỌI request AI trả 500 (lỗi không được map, rơi vào handler
        catch-all).
        """
        assert set(_PROVIDERS) == SUPPORTED_LLM_PROVIDERS

    def test_admin_schema_accepts_exactly_the_supported_providers(self) -> None:
        field = AdminUpdateLLMProviderRequest.model_fields["llm_provider"]
        assert frozenset(get_args(field.annotation)) == SUPPORTED_LLM_PROVIDERS

    def test_every_supported_provider_has_models(self) -> None:
        """Thêm nhà cung cấp vào Literal mà quên khai model -> fail ở đây.

        Không có test này thì admin chọn được nhà cung cấp đó nhưng
        `get_llm_provider` từ chối mọi model, tức tính năng AI chết mà PATCH
        vẫn báo thành công.
        """
        assert set(SUPPORTED_LLM_MODELS) == SUPPORTED_LLM_PROVIDERS
        assert all(SUPPORTED_LLM_MODELS[name] for name in SUPPORTED_LLM_PROVIDERS)

    def test_default_provider_is_supported(self) -> None:
        assert DEFAULT_LLM_PROVIDER in SUPPORTED_LLM_PROVIDERS

    def test_default_model_belongs_to_the_default_provider(self) -> None:
        assert DEFAULT_LLM_MODEL in SUPPORTED_LLM_MODELS[DEFAULT_LLM_PROVIDER]


def _a_model_for(provider: str) -> str:
    """Một model hợp lệ bất kỳ của nhà cung cấp — sorted() để test tất định."""
    return sorted(SUPPORTED_LLM_MODELS[provider])[0]


class TestGetLLMProvider:
    @pytest.mark.parametrize("name", sorted(SUPPORTED_LLM_PROVIDERS))
    def test_returns_a_provider_instance(self, name: str) -> None:
        assert isinstance(get_llm_provider(name, _a_model_for(name)), BaseLLMProvider)

    def test_is_case_insensitive(self) -> None:
        model = _a_model_for("groq")
        assert type(get_llm_provider("GROQ", model)) is type(get_llm_provider("groq", model))

    def test_unknown_provider_raises_ai_generation_error(self) -> None:
        """AIGenerationError chứ không phải ValueError trần: có sẵn đường ra 502.

        ValueError trần rơi xuống handler cuối và thành 500 trống trơn — đúng lỗi
        mà #92 đã sửa cho cả tầng này.
        """
        with pytest.raises(AIGenerationError, match="không hỗ trợ"):
            get_llm_provider("not-a-real-provider", DEFAULT_LLM_MODEL)

    def test_model_from_another_provider_is_rejected(self) -> None:
        """Model có thật nhưng của nhà cung cấp KHÁC vẫn phải bị từ chối."""
        with pytest.raises(AIGenerationError, match="không thuộc nhà cung cấp"):
            get_llm_provider("gemini", _a_model_for("groq"))
