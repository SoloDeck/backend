from typing import Any

from pydantic import BaseModel, Field, field_validator

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

    # Phạm vi KHÔNG bao gồm — AI suy ra từ chính lời khách: khách nói "cần website bán
    # hàng" thì viết nội dung/hình ảnh sản phẩm, tên miền, hosting thường KHÔNG nằm trong.
    # Đây là dòng phòng thủ chống scope creep.  #Huynh
    out_of_scope: list[str] = Field(default_factory=list)

    # --- Đầu vào cho bộ định giá (pricing.py) ---------------------------------------
    #
    # AI KHÔNG xuất ra con số tiền nào. Nó chỉ chấm ba thứ dưới đây, và `pricing.py` mới
    # nhân ra tiền. Đó là ranh giới cốt lõi của cả module: LLM phán TƯƠNG ĐỐI (việc nó
    # làm tốt), code tính TUYỆT ĐỐI (việc nó làm đúng).  #Huynh

    complexity: str = "normal"
    complexity_reason: str = ""
    scale: str = "normal"
    scale_reason: str = ""

    # [{"label": "Quản lý kho", "weight": 25}, ...] — tỉ trọng CÔNG SỨC, không phải giờ,
    # không phải tiền. Không cần cộng thành 100: code tự chuẩn hoá.
    line_item_weights: list[dict[str, Any]] = Field(default_factory=list)

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

    @field_validator("scope_of_work", "deliverables", "out_of_scope", mode="before")
    @classmethod
    def _coerce_text_list(cls, value: Any) -> list[str]:
        return _to_text_list(value)

    @field_validator("complexity_reason", "scale_reason", mode="before")
    @classmethod
    def _coerce_reason(cls, value: Any) -> str:
        return _to_text(value)

    @field_validator("line_item_weights", mode="before")
    @classmethod
    def _coerce_weights(cls, value: Any) -> list[dict[str, Any]]:
        """Model hay trả về đủ kiểu: mảng chuỗi, object thay vì mảng, weight là chuỗi "30%".

        Bỏ qua thứ không hiểu được thay vì ném lỗi — hạng mục hỏng thì mất một dòng trong
        bảng, còn ném lỗi là mất cả bản báo giá.  #Huynh
        """
        if isinstance(value, dict):
            value = [{"label": k, "weight": v} for k, v in value.items()]
        if not isinstance(value, list):
            return []

        items: list[dict[str, Any]] = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            label = _to_text(entry.get("label") or entry.get("name"))
            raw_weight = entry.get("weight", entry.get("percent"))
            try:
                weight = int(float(str(raw_weight).strip().rstrip("%")))
            except (TypeError, ValueError):
                continue
            if label and weight > 0:
                items.append({"label": label, "weight": weight})
        return items
