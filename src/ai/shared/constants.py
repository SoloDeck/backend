"""
Shared constants used across the AI module.
"""

# ==========================================================
# Supported LLM providers
# ==========================================================

SUPPORTED_LLM_PROVIDERS: set[str] = {
    "groq",
    "gemini",
    "ollama",
}


# ==========================================================
# Supported models per provider
# ==========================================================

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

DEFAULT_LLM_PROVIDER = "groq"

DEFAULT_LLM_MODEL = "openai/gpt-oss-120b"
