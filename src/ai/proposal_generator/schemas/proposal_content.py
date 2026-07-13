from typing import Any

from pydantic import BaseModel, field_validator


def _to_text(value: Any) -> str:
    """Ép mọi thứ model trả về thành văn bản đọc được.  #Huynh"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_to_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_to_text(val)}" for key, val in value.items())
    return str(value)


def _to_text_list(value: Any) -> list[str]:
    """Ép mọi thứ model trả về thành danh sách chuỗi.  #Huynh"""
    if value is None:
        return []
    if isinstance(value, list):
        return [_to_text(item) for item in value]
    if isinstance(value, dict):
        return [f"{key}: {_to_text(val)}" for key, val in value.items()]
    return [_to_text(value)]


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
