"""
Shared constants used across the AI module.
"""

from typing import Literal, get_args

# NGUỒN SỰ THẬT DUY NHẤT cho danh sách nhà cung cấp LLM.
#
# Trước đây danh sách này được viết tay ở BA nơi: Literal trong
# AdminUpdateLLMProviderRequest, set SUPPORTED_LLM_PROVIDERS ở đây, và chuỗi
# if/elif trong get_llm_provider(). Thêm một nhà cung cấp mà quên một trong ba
# chỗ sẽ gây lỗi lệch pha khó thấy (API trả 422 cho nhà cung cấp mà phần còn
# lại của codebase tin là đã hỗ trợ, hoặc ngược lại là 500 khi factory không
# dựng được). Khai báo Literal làm gốc rồi suy ra các dạng khác để chỉ còn MỘT
# chỗ cần sửa.
# "openai" CHƯA có ở đây: OpenAIProvider hiện là lớp rỗng (`... # implement
# later`) nên không cài đặt phương thức trừu tượng `generate` — gọi
# OpenAIProvider() ném TypeError. Khi nó còn nằm trong Literal, admin vẫn
# PATCH /admin/ai-provider sang "openai" và nhận 200, sau đó MỌI request AI
# trả 500 cho tới khi có người đổi lại. Thêm lại dòng "openai" ngay khi
# OpenAIProvider được cài đặt thật — test test_every_supported_provider_is_
# constructible sẽ báo nếu hai bên lệch nhau.
LLMProviderName = Literal[
    "groq",
    "gemini",
]

SUPPORTED_LLM_PROVIDERS: frozenset[str] = frozenset(get_args(LLMProviderName))

DEFAULT_LLM_PROVIDER: LLMProviderName = "groq"
