"""
Shared constants used across the AI module.
"""

from typing import Literal, get_args

# ==========================================================
# Supported LLM providers
# ==========================================================

# NGUỒN SỰ THẬT DUY NHẤT cho danh sách nhà cung cấp LLM.
#
# Trước đây danh sách này được viết tay ở BA nơi: Literal trong
# AdminUpdateLLMProviderRequest, set SUPPORTED_LLM_PROVIDERS ở đây, và chuỗi
# if/elif trong get_llm_provider(). Thêm một nhà cung cấp mà quên một trong ba
# chỗ sẽ gây lỗi lệch pha khó thấy (API trả 422 cho nhà cung cấp mà phần còn
# lại của codebase tin là đã hỗ trợ, hoặc ngược lại là 500 khi factory không
# dựng được). Khai báo Literal làm gốc rồi suy ra các dạng khác để chỉ còn MỘT
# chỗ cần sửa.
#
# "openai" CHƯA có ở đây: OpenAIProvider hiện là lớp rỗng (`... # implement
# later`) nên không cài đặt phương thức trừu tượng `generate` — gọi
# OpenAIProvider() ném TypeError. Khi nó còn nằm trong Literal, admin vẫn
# PATCH /admin/ai-provider sang "openai" và nhận 200, sau đó MỌI request AI
# trả 500 cho tới khi có người đổi lại. Thêm lại dòng "openai" ngay khi
# OpenAIProvider được cài đặt thật — test test_every_supported_provider_is_
# constructible sẽ báo nếu hai bên lệch nhau.
#
# "ollama" thì CÓ: OllamaProvider đã cài đặt thật, gọi HTTP tới `ollama_base_url`.
LLMProviderName = Literal[
    "groq",
    "gemini",
    "ollama",
]

SUPPORTED_LLM_PROVIDERS: frozenset[str] = frozenset(get_args(LLMProviderName))


# ==========================================================
# Supported models per provider
# ==========================================================

# Khoá của dict PHẢI phủ đúng LLMProviderName — thêm nhà cung cấp vào Literal mà
# quên khai model ở đây thì admin chọn được nhưng không dựng nổi provider. Test
# test_every_supported_provider_has_models canh đúng chỗ lệch đó.
#
# Groq đã GỠ toàn bộ dòng Llama khỏi API (gọi `llama-3.3-70b-versatile` trả
# 404 `model_not_found`), nên mọi tính năng AI chết đồng loạt: bấm "Tạo Báo Giá AI" là
# vòng xoay quay mãi rồi rơi về nhánh lỗi.
#
# Model còn phục vụ ở dưới có cùng cửa sổ ngữ cảnh 131k và có `response_format=json_object`
# — điều kiện bắt buộc vì cả ba bộ sinh (báo giá, hợp đồng, chấm điểm lead) đều đọc JSON
# có cấu trúc chứ không đọc văn xuôi.
#
# Danh sách model đổi theo thời gian; kiểm bằng `GET https://api.groq.com/openai/v1/models`
# với chính khoá đang dùng, đừng đoán theo tên.  #Huynh

SUPPORTED_LLM_MODELS: dict[str, set[str]] = {
    "groq": {
        "openai/gpt-oss-120b",
    },
    "gemini": {
        "gemini-2.5-flash",
    },
    "ollama": {
        "qwen3:4b",
    },
}


# ==========================================================
# Default configuration
# ==========================================================

DEFAULT_LLM_PROVIDER: LLMProviderName = "groq"

DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
