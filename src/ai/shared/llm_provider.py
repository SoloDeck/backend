"""Provider abstraction for all LLM vendors."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from google import genai
from google.genai.types import GenerateContentConfig
from groq import Groq

from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings


@dataclass
class LLMUsage:
    model_used: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage | None = None


class BaseLLMProvider(ABC):
    """Interface every LLM provider must implement."""

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        temperature: float = 0,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError


class GroqProvider(BaseLLMProvider):
    MODEL = "llama-3.3-70b-versatile"

    def __init__(self):
        api_key = settings.groq_api_key
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        self.client = Groq(api_key=api_key)

    async def generate(
        self,
        *,
        prompt: str,
        temperature: float = 0,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:

        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=temperature,
            seed=seed,
            response_format={"type": "json_object"} if json_mode else None,
        )

        usage = extract_usage(
            response,
            model=getattr(response, "model", None) or self.MODEL,
        )

        return LLMResponse(
            text=response.choices[0].message.content or "",
            usage=usage,
        )
    # contains all the current Groq logic


class GeminiProvider(BaseLLMProvider):
    MODEL = "gemini-2.5-flash"

    def __init__(self):
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=api_key)

    async def generate(
        self,
        *,
        prompt: str,
        temperature: float = 0,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:

        config = GenerateContentConfig(
            temperature=temperature,
            seed=seed,
            response_mime_type=(
                "application/json"
                if json_mode
                else "text/plain"
            ),
        )

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.MODEL,
            contents=prompt,
            config=config,
        )

        return LLMResponse(
            text=response.text,
            usage=None,
        )
    # contains all current Gemini logic


class OpenAIProvider(BaseLLMProvider):
    ...
    # implement later


# Khoá của dict phải phủ đúng LLMProviderName — test
# test_every_supported_provider_is_constructible canh việc này, nên thêm nhà
# cung cấp vào Literal mà quên map ở đây sẽ fail test thay vì fail 500 lúc chạy.
_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    # "openai": OpenAIProvider — bỏ ra cho tới khi OpenAIProvider cài đặt
    # `generate`; hiện là lớp rỗng nên không khởi tạo được (xem constants.py).
}


def get_llm_provider(provider: str) -> BaseLLMProvider:
    """Return the configured provider."""

    try:
        return _PROVIDERS[provider.lower()]()
    except KeyError:
        # Giá trị này đọc từ ai_provider_configuration, và schema của endpoint
        # admin đã chặn giá trị lạ — nên tới được đây nghĩa là DB bị sửa tay
        # hoặc nhà cung cấp bị xoá khỏi map mà còn trong Literal. Đây là lỗi
        # cấu hình phía server (500), không phải lỗi của client.
        raise ValueError(f"Unsupported LLM provider: {provider}") from None
