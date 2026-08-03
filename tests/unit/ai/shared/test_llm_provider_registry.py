"""Danh sách nhà cung cấp LLM phải nhất quán giữa các nơi dùng nó.

Trước đây danh sách được viết tay ở ba chỗ (Literal của schema admin, set
SUPPORTED_LLM_PROVIDERS, chuỗi if/elif trong get_llm_provider). Giờ tất cả suy
ra từ LLMProviderName; các test dưới đây canh để chúng không lệch nhau lần nữa.
"""

from typing import get_args

import pytest

from src.ai.shared.constants import (
    DEFAULT_LLM_PROVIDER,
    SUPPORTED_LLM_PROVIDERS,
    LLMProviderName,
)
from src.ai.shared.llm_provider import _PROVIDERS, BaseLLMProvider, get_llm_provider
from src.modules.admin.schemas.request import AdminUpdateLLMProviderRequest


class TestProviderRegistryConsistency:
    def test_supported_set_matches_the_literal(self) -> None:
        assert frozenset(get_args(LLMProviderName)) == SUPPORTED_LLM_PROVIDERS

    def test_every_supported_provider_is_constructible(self) -> None:
        """Thêm nhà cung cấp vào Literal mà quên map trong _PROVIDERS -> fail ở đây.

        Nếu không có test này, sai sót chỉ lộ ra khi admin đổi sang nhà cung cấp
        đó và MỌI request AI trả 500 (ValueError không được map, rơi vào handler
        catch-all).
        """
        assert set(_PROVIDERS) == SUPPORTED_LLM_PROVIDERS

    def test_admin_schema_accepts_exactly_the_supported_providers(self) -> None:
        field = AdminUpdateLLMProviderRequest.model_fields["llm_provider"]
        assert frozenset(get_args(field.annotation)) == SUPPORTED_LLM_PROVIDERS

    def test_default_provider_is_supported(self) -> None:
        assert DEFAULT_LLM_PROVIDER in SUPPORTED_LLM_PROVIDERS


class TestGetLLMProvider:
    @pytest.mark.parametrize("name", sorted(SUPPORTED_LLM_PROVIDERS))
    def test_returns_a_provider_instance(self, name: str) -> None:
        assert isinstance(get_llm_provider(name), BaseLLMProvider)

    def test_is_case_insensitive(self) -> None:
        assert type(get_llm_provider("GROQ")) is type(get_llm_provider("groq"))

    def test_unknown_provider_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_llm_provider("not-a-real-provider")
