"""Đo token và ước tính chi phí mỗi lần gọi Groq.

Bảng ``ai_cost_records`` có sẵn từ lâu (module, model, input/output tokens, chi phí,
trạng thái), endpoint ``GET /admin/ai-costs`` cũng có sẵn — nhưng **không ai ghi vào**.
Bảng 0 dòng, nên màn hình admin sẽ luôn rỗng. Đúng bệnh của ``usage_records``: hạ tầng
đủ, thiếu đúng người gọi.

Groq trả về ``response.usage`` với số token thật của từng lần gọi. Trước giờ ta vứt đi.
  #Huynh
"""

from decimal import Decimal
from typing import Any

# Đơn giá Groq cho llama-4-scout-17b (USD / 1 triệu token), tại thời điểm viết.
#
# Đây là ƯỚC TÍNH, không phải hoá đơn: giá có thể đổi, và Groq tính tiền theo bảng giá
# của họ chứ không theo con số ta lưu. Cột trong DB cũng tên là `estimated_cost_usd` —
# giao diện phải nói rõ là "ước tính", đừng để ai tưởng đây là số tiền đã trả.  #Huynh
PRICE_PER_MILLION_INPUT = Decimal("0.11")
PRICE_PER_MILLION_OUTPUT = Decimal("0.34")

_MILLION = Decimal("1000000")


# Đơn giá Gemini (USD / 1 triệu token), bậc trả phí, tại thời điểm viết (09/2026).
# Kiểm lại ở https://ai.google.dev/gemini-api/docs/pricing trước khi tin con số này.
# Model không có trong bảng thì chi phí ghi 0 — SỐ TOKEN vẫn đúng, chỉ phần tiền là
# chưa ước tính được. Thà để 0 còn hơn đoán một đơn giá rồi admin tin theo.  #Huynh
GEMINI_PRICES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
}


def usage_record(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    price_in: Decimal = Decimal(0),
    price_out: Decimal = Decimal(0),
) -> dict[str, Any]:
    """Dạng DUY NHẤT mà mọi nhà cung cấp trả về cho `AiUsageService.record_cost`.

    Có hàm này vì từng có hai dạng song song: Groq trả dict, Ollama trả dataclass. Bên
    ghi chi phí gọi `usage.get(...)`, nên chọn Ollama là mọi tính năng AI nổ
    AttributeError ngay SAU khi model đã trả lời xong. Gemini thì trả None, nên bảng chi
    phí AI của admin luôn trống khi chạy Gemini.  #Huynh

    `price_in`/`price_out` là USD cho 1 triệu token.
    """
    cost = (
        Decimal(input_tokens) / _MILLION * price_in
        + Decimal(output_tokens) / _MILLION * price_out
    )
    return {
        "model_used": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost.quantize(Decimal("0.000001")),
    }


def extract_usage(response: Any, *, model: str) -> dict[str, Any]:
    """Bóc số token từ response của Groq và ước tính chi phí."""
    usage = getattr(response, "usage", None)
    return usage_record(
        model=model,
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        price_in=PRICE_PER_MILLION_INPUT,
        price_out=PRICE_PER_MILLION_OUTPUT,
    )


def extract_gemini_usage(response: Any, *, model: str) -> dict[str, Any]:
    """Bóc số token từ `usage_metadata` của Gemini.

    Token ra = `candidates_token_count` + `thoughts_token_count`: dòng 2.5 "nghĩ" trước khi
    trả lời, và Google tính tiền phần nghĩ theo đơn giá token ra. Bỏ phần đó thì số
    token ra (và tiền) thấp hơn thật nhiều lần.
    """
    meta = getattr(response, "usage_metadata", None)
    price_in, price_out = GEMINI_PRICES_PER_MILLION.get(model, (Decimal(0), Decimal(0)))
    return usage_record(
        model=model,
        input_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(meta, "candidates_token_count", 0) or 0)
        + int(getattr(meta, "thoughts_token_count", 0) or 0),
        price_in=price_in,
        price_out=price_out,
    )
