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
    # Groq đã GỠ toàn bộ dòng Llama khỏi API (gọi `llama-3.3-70b-versatile` trả
    # 404 `model_not_found`), nên mọi tính năng AI chết đồng loạt: bấm "Tạo Báo Giá AI" là
    # vòng xoay quay mãi rồi rơi về nhánh lỗi.
    #
    # Đổi sang model còn phục vụ, cùng cửa sổ ngữ cảnh 131k và có `response_format=json_object`
    # — điều kiện bắt buộc vì cả ba bộ sinh (báo giá, hợp đồng, chấm điểm lead) đều đọc JSON
    # có cấu trúc chứ không đọc văn xuôi.
    #
    # Danh sách model đổi theo thời gian; kiểm bằng `GET https://api.groq.com/openai/v1/models`
    # với chính khoá đang dùng, đừng đoán theo tên.  #Huynh
    MODEL = "openai/gpt-oss-120b"

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


def get_llm_provider(provider: str) -> BaseLLMProvider:
    """Return the configured provider."""

    provider = provider.lower()

    if provider == "groq":
        return GroqProvider()

    if provider == "gemini":
        return GeminiProvider()

    if provider == "openai":
        return OpenAIProvider()

    raise ValueError(f"Unsupported LLM provider: {provider}")
