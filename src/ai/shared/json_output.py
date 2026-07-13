"""Bóc khối JSON ra khỏi câu trả lời của LLM.

Dùng chung cho mọi AI chain. Trước đây mỗi chain tự viết một bản riêng, và khi
sửa bug ở một nơi thì nơi kia bị bỏ quên — đúng cái đã xảy ra với cuộc di trú
sang Groq. Gom về một chỗ để chuyện đó không lặp lại.  #Huynh
"""

import json
import re
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any]:
    """Trả về dict JSON đầu tiên tìm được trong ``raw``.

    Ném ``json.JSONDecodeError`` nếu không bóc được. Bên gọi tự bọc lại thành
    exception của domain mình (``AIOutputParseError``, ``ValueError``...).

    Model không phải lúc nào cũng trả JSON thuần. Gặp thật trên production:
    llama-4-scout thêm một câu dẫn trước code fence, ví dụ

        Here is the draft qualification result:
        ```
        {"project_type": "E-commerce Website", ...}
        ```

    Bản cũ chỉ cắt fence khi CẢ chuỗi bắt đầu bằng ```, nên chỉ cần có câu dẫn là
    ``json.loads`` vỡ và kết quả AI (vốn hoàn toàn đúng) bị vứt đi.  #Huynh
    """
    text = raw.strip()

    # Cắt fence khi câu trả lời được bọc fence ngay từ đầu.  #Huynh
    if text.startswith("```json"):
        text = text.removeprefix("```json").strip()
    elif text.startswith("```"):
        text = text.removeprefix("```").strip()
    if text.endswith("```"):
        text = text.removesuffix("```").strip()

    try:
        parsed: dict[str, Any] = json.loads(text)
        return parsed
    except json.JSONDecodeError:
        pass  # không parse thẳng được thì thử bóc bên dưới  #Huynh

    # Mọi trường hợp còn lại (câu dẫn, model nói thêm sau JSON, fence nằm giữa):
    # lấy khối {...} ngoài cùng.
    # Cố tình dùng greedy (.* chứ không phải .*?): non-greedy sẽ dừng ở dấu }
    # ĐẦU TIÊN, mà kết quả AI có object lồng nhau (detected_signals là mảng các
    # object) nên sẽ bị cắt cụt.  #Huynh
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is not None:
        extracted: dict[str, Any] = json.loads(match.group(0))
        return extracted

    raise json.JSONDecodeError("No JSON object found in model output", text, 0)
