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


def extract_usage(response: Any, *, model: str) -> dict[str, Any]:
    """Bóc số token từ response của Groq và ước tính chi phí."""
    usage = getattr(response, "usage", None)

    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    cost = (
        Decimal(input_tokens) / _MILLION * PRICE_PER_MILLION_INPUT
        + Decimal(output_tokens) / _MILLION * PRICE_PER_MILLION_OUTPUT
    )

    return {
        "model_used": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost.quantize(Decimal("0.000001")),
    }
