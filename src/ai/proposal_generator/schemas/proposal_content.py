from typing import Any

from pydantic import BaseModel, field_validator

# Hai hàm ép kiểu này giờ nằm ở src/ai/shared/text_coercion.py vì contract_generator
# cũng cần đúng như vậy.  #Huynh
from src.ai.shared.text_coercion import to_text as _to_text
from src.ai.shared.text_coercion import to_text_list as _to_text_list


class ProposalContent(BaseModel):
    """Nội dung báo giá do AI sinh ra.

    Đây là schema NỘI BỘ của AI, không phải hợp đồng API — `contracts/openapi.yaml`
    khai `ProposalContentDTO` là shape khác, dành cho frontend. Nên nới lỏng đầu vào
    ở đây không đụng gì tới hợp đồng: đầu ra vẫn đúng kiểu như cũ.  #Huynh
    """

    project_overview: str

    scope_of_work: list[str]

    deliverables: list[str]

    timeline: str

    pricing: str

    payment_terms: str

    assumptions: str

    # llama-4-scout KHÔNG ổn định: prompt đã yêu cầu `"pricing": "..."` (chuỗi) nhưng
    # model thỉnh thoảng trả về object, ví dụ {"total": "50.000.000 VND", "breakdown":
    # [...]}. Khi đó pydantic ném ValidationError → endpoint 500. Cùng một request, lần
    # được lần không. Thay vì tin model làm đúng, ta ép kiểu ở đây.  #Huynh
    @field_validator(
        "project_overview", "timeline", "pricing", "payment_terms", "assumptions", mode="before"
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _to_text(value)

    @field_validator("scope_of_work", "deliverables", mode="before")
    @classmethod
    def _coerce_text_list(cls, value: Any) -> list[str]:
        return _to_text_list(value)
