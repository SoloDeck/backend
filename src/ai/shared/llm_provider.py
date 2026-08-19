"""Provider abstraction for all LLM vendors."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

import httpx
from google import genai
from google.genai.types import GenerateContentConfig
from groq import Groq

from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings

from src.ai.shared.constants import (
    SUPPORTED_LLM_MODELS,
)


# ==========================================================
# Response models
# ==========================================================

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


# ==========================================================
# Base Provider
# ==========================================================

class BaseLLMProvider(ABC):
    """Interface every LLM provider must implement."""

    def __init__(self, model: str):
        self.model = model

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


# ==========================================================
# Groq
# ==========================================================

class GroqProvider(BaseLLMProvider):
    # Model không còn cố định ở đây — admin chọn trong `SUPPORTED_LLM_MODELS`
    # (xem ghi chú về việc Groq gỡ dòng Llama trong `src/ai/shared/constants.py`).

    def __init__(self, model: str):
        super().__init__(model)

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
            model=self.model,
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
            model=getattr(response, "model", None) or self.model,
        )

        return LLMResponse(
            text=response.choices[0].message.content or "",
            usage=usage,
        )


# ==========================================================
# Gemini
# ==========================================================

class GeminiProvider(BaseLLMProvider):

    def __init__(self, model: str):
        super().__init__(model)

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
            model=self.model,
            contents=prompt,
            config=config,
        )

        return LLMResponse(
            text=response.text,
            usage=None,
        )

# ==========================================================
# Ollama
# ==========================================================

class OllamaProvider(BaseLLMProvider):

    def __init__(self, model: str):
        super().__init__(model)

        self.base_url = settings.ollama_base_url.rstrip("/")

    async def generate(
        self,
        *,
        prompt: str,
        temperature: float = 0,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if seed is not None:
            payload["options"]["seed"] = seed

        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        input_tokens = int(data.get("prompt_eval_count", 0))
        output_tokens = int(data.get("eval_count", 0))

        usage = LLMUsage(
            model_used=data.get("model", self.model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=Decimal("0"),
        )

        return LLMResponse(
            text=data.get("response", ""),
            usage=usage,
        )


# ==========================================================
# Factory
# ==========================================================

# Khoá của dict phải phủ đúng LLMProviderName — test
# test_every_supported_provider_is_constructible canh việc này, nên thêm nhà
# cung cấp vào Literal mà quên map ở đây sẽ fail test thay vì fail 500 lúc chạy.
_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    # "openai": OpenAIProvider — bỏ ra cho tới khi OpenAIProvider cài đặt
    # `generate`; hiện là lớp rỗng nên không khởi tạo được (xem constants.py).
}


def get_llm_provider(
    provider: str,
    model: str,
) -> BaseLLMProvider:
    """
    Return the configured provider using the requested model.
    """

    key = provider.lower()

    supported = SUPPORTED_LLM_MODELS.get(key)

    if supported is None:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    if model not in supported:
        raise ValueError(
            f"Model '{model}' is not supported by provider '{provider}'."
        )

    try:
        return _PROVIDERS[key](model)
    except KeyError:
        # Tới được đây nghĩa là provider có trong SUPPORTED_LLM_MODELS nhưng
        # thiếu ở _PROVIDERS — lỗi cấu hình phía server, không phải lỗi client.
        raise ValueError(f"Unsupported LLM provider: {provider}") from None
