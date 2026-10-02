"""Câu báo lỗi tiếng Việt cho trường chuỗi nhập quá dài.

Vì sao có file này: cột Postgres `VARCHAR(n)` từ chối chuỗi dài hơn n ký tự bằng
`StringDataRightTruncationError`. Schema không chặn trước thì lỗi đó đi xuyên qua mọi tầng và
thành HTTP 500 "An unexpected error occurred" — người dùng không biết mình gõ dài quá, còn log
server thì đầy stack trace của một lỗi vốn là LỖI ĐẦU VÀO. Chặn bằng `max_length` ngay ở schema
thì FastAPI trả 422 kèm tên trường.

Nhưng câu mặc định của Pydantic ("String should have at most 200 characters") là tiếng Anh, và
không nói trường nào bị dài: web ghép các câu trong `error.details` thành MỘT dòng toast mà
không kèm tên trường. Lớp này đổi nó thành "Loại dự án tối đa 200 ký tự (bạn đã nhập 201)".

Khai báo MỘT chỗ duy nhất, ngay trên `Field`:

    project_type: str | None = Field(default=None, max_length=200, title="Loại dự án")

Giới hạn lấy từ chính `max_length`, tên trường lấy từ `title` (không có `title` thì dùng tên
trường) — không phải viết lại con số ở chỗ khác. `max_length` PHẢI đúng bằng độ dài cột trong
`infrastructure/database/models.py`; test `test_request_length_limits.py` canh chỗ lệch đó.
"""

from typing import Any

from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError


def _max_length_of(metadata: list[Any]) -> int | None:
    """Giới hạn `max_length` của một trường, nằm trong metadata mà `Field(...)` sinh ra."""
    for item in metadata:
        limit = getattr(item, "max_length", None)
        if isinstance(limit, int):
            return limit
    return None


class LengthLimitedModel(BaseModel):
    """Base cho schema request có trường chuỗi giới hạn độ dài.

    Chỉ ĐỔI CÂU BÁO LỖI: việc chặn vẫn do `max_length` của Pydantic làm (nên OpenAPI vẫn có
    `maxLength`). Validator này chạy TRƯỚC phép kiểm của Pydantic, thấy chuỗi quá dài thì ném
    câu tiếng Việt thay cho câu tiếng Anh. Giá trị không phải chuỗi (số, `None`, dict...) đi
    qua nguyên vẹn để Pydantic tự xử như cũ.
    """

    @field_validator("*", mode="before")
    @classmethod
    def _bao_loi_do_dai_bang_tieng_viet(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, str) or info.field_name is None:
            return value

        field = cls.model_fields.get(info.field_name)
        if field is None:
            return value

        limit = _max_length_of(field.metadata)
        if limit is not None and len(value) > limit:
            # Cùng `type` với lỗi gốc của Pydantic để ai đang phân nhánh theo mã lỗi không vỡ.
            raise PydanticCustomError(
                "string_too_long",
                "{label} tối đa {max_length} ký tự (bạn đã nhập {actual_length})",
                {
                    "label": field.title or info.field_name,
                    "max_length": limit,
                    "actual_length": len(value),
                },
            )
        return value
