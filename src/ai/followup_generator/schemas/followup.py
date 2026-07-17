"""Schema cho tin nhắn nhắc follow-up do AI soạn."""

from typing import Any

from pydantic import BaseModel, field_validator

from src.ai.shared.text_coercion import to_text


class FollowUpMessage(BaseModel):
    """Tin nhắn nhắc khách, AI soạn sẵn để freelancer đọc lại rồi gửi.

    ``openapi.yaml`` khai ``FollowUpGenerationResponse`` chỉ có ``message_text`` +
    ``generation_id``. ``subject`` là phần THÊM (tiện khi gửi email), không phá hợp đồng
    vì schema không khoá ``additionalProperties``.  #Huynh
    """

    message_text: str

    # Tiêu đề email — để trống khi gửi qua Zalo/SMS.
    subject: str = ""

    # llama-4-scout hay trả mảng gạch đầu dòng dù prompt yêu cầu một đoạn văn. Ép kiểu
    # ở đây thay vì để pydantic ném ValidationError rồi endpoint 500 — đúng cách
    # contract_generator và proposal_generator đang xử lý.  #Huynh
    @field_validator("message_text", "subject", mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return to_text(value)
