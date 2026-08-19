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
from src.shared.exceptions.domain import AIGenerationError, DomainError

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
    """Interface every LLM provider must implement.

    Cài đặt cụ thể viết vào `_generate`, KHÔNG override `generate`. `generate` là lớp
    vỏ dịch mọi lỗi của SDK nhà cung cấp thành `AIGenerationError`.
    """

    async def generate(
        self,
        *,
        prompt: str,
        temperature: float = 0,
        seed: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Gọi nhà cung cấp, dịch lỗi của họ sang lỗi miền của mình.

        SDK mỗi hãng ném một họ exception riêng (`groq.PermissionDeniedError`,
        `google.genai.errors.ClientError`...). Không hãng nào là DomainError nên chúng
        rơi thẳng xuống handler cuối cùng và thành 500 "An unexpected error occurred" —
        client không biết là do AI, còn nguyên nhân thật chỉ nằm trong log server.

        Đã trả giá thật vì chuyện này: key Groq bị chặn theo vùng, `/deals/{id}/qualify`
        và `/proposals/ai-generate` cùng ném 500 trống trơn, mất một lúc mới lần ra là
        hỏng ở nhà cung cấp chứ không phải code mình.

        `AIGenerationError` đã có sẵn đường ra 502 trong `shared/exceptions/http.py`.
        Bọc ở lớp cha để mọi provider — kể cả cái viết sau này — đều được dịch, thay vì
        trông chờ từng chain nhớ tự bắt.  #Huynh
        """
        try:
            return await self._generate(
                prompt=prompt,
                temperature=temperature,
                seed=seed,
                json_mode=json_mode,
            )
        except DomainError:
            # AIOutputParseError và họ hàng đã đúng nghĩa rồi, để nguyên.
            raise
        except Exception as exc:
            raise AIGenerationError(
                f"Nhà cung cấp AI ({type(self).__name__}) gọi không thành công: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    @abstractmethod
    async def _generate(
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

    async def _generate(
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

    async def _generate(
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
            response_mime_type=("application/json" if json_mode else "text/plain"),
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
    """Return the configured provider.

    Hỏng ở khâu DỰNG provider cũng phải ra `AIGenerationError` y như hỏng lúc GỌI. Cả
    hai đều là "phần AI không dùng được lúc này", và cùng cần 502 kèm lý do. Trước đây
    khâu này ném `ValueError`/`RuntimeError`/`TypeError` trần: thiếu key thì RuntimeError,
    còn chọn 'openai' thì `OpenAIProvider()` ném TypeError vì lớp đó chưa cài `_generate`
    nên vẫn là abstract. Cả ba đều rơi xuống handler cuối và thành 500 trống trơn.  #Huynh
    """
    key = provider.lower()

    try:
        if key == "groq":
            return GroqProvider()
        if key == "gemini":
            return GeminiProvider()
    except DomainError:
        raise
    except Exception as exc:
        raise AIGenerationError(
            f"Không khởi tạo được nhà cung cấp AI '{key}': {type(exc).__name__}: {exc}"
        ) from exc

    if key == "openai":
        raise AIGenerationError(
            "Nhà cung cấp AI 'openai' chưa được cài đặt. Đổi sang 'groq' hoặc 'gemini' "
            "qua PATCH /admin/ai-provider."
        )

    raise AIGenerationError(f"Nhà cung cấp AI không hỗ trợ: '{provider}'")
