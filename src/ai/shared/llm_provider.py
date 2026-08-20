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

from src.ai.shared.constants import SUPPORTED_LLM_MODELS
from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings
from src.shared.exceptions.domain import AIGenerationError, DomainError


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
    """Interface every LLM provider must implement.

    Cài đặt cụ thể viết vào `_generate`, KHÔNG override `generate`. `generate` là lớp
    vỏ dịch mọi lỗi của SDK nhà cung cấp thành `AIGenerationError`.

    Model do admin chọn và được truyền vào lúc dựng (xem `SUPPORTED_LLM_MODELS`), nên
    không còn hằng MODEL cố định trong từng lớp nữa.
    """

    def __init__(self, model: str):
        self.model = model

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

    async def _generate(
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


class OpenAIProvider(BaseLLMProvider):
    ...
    # implement later


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
    # `_generate`; hiện là lớp rỗng nên không khởi tạo được (xem constants.py).
}


def get_llm_provider(
    provider: str,
    model: str,
) -> BaseLLMProvider:
    """Return the configured provider using the requested model.

    MỌI lối thoát ở đây đều là `AIGenerationError`, không phải ValueError trần.
    Hỏng ở khâu DỰNG provider cũng là "phần AI không dùng được lúc này" y như hỏng
    lúc GỌI, và cùng cần 502 kèm lý do. Trước đây khâu này ném
    `ValueError`/`RuntimeError`/`TypeError` trần: thiếu key thì RuntimeError, còn
    chọn 'openai' thì `OpenAIProvider()` ném TypeError vì lớp đó chưa cài
    `_generate` nên vẫn là abstract. Cả ba đều rơi xuống handler cuối và thành 500
    trống trơn.  #Huynh

    `AdminService.update_ai_provider_configuration` gọi hàm này để DỰNG THỬ trước
    khi ghi cấu hình, và bắt rộng rồi đổi thành 422 — nên admin chọn nhầm vẫn nhận
    lỗi đúng nghĩa chứ không phải 502.
    """
    key = provider.lower()

    supported = SUPPORTED_LLM_MODELS.get(key)

    if supported is None:
        raise AIGenerationError(f"Nhà cung cấp AI không hỗ trợ: '{provider}'")

    if model not in supported:
        raise AIGenerationError(
            f"Model '{model}' không thuộc nhà cung cấp '{provider}'."
        )

    cls = _PROVIDERS.get(key)
    if cls is None:
        # provider có trong SUPPORTED_LLM_MODELS nhưng thiếu ở _PROVIDERS — lỗi
        # cấu hình phía server. 'openai' rơi vào đây cho tới khi được cài đặt thật.
        raise AIGenerationError(
            f"Nhà cung cấp AI '{key}' chưa được cài đặt. Đổi sang một nhà cung cấp "
            f"khác qua PATCH /admin/ai-provider."
        )

    try:
        return cls(model)
    except DomainError:
        raise
    except Exception as exc:
        raise AIGenerationError(
            f"Không khởi tạo được nhà cung cấp AI '{key}': {type(exc).__name__}: {exc}"
        ) from exc
