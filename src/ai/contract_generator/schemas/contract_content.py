"""Schema cho phần nội dung hợp đồng do AI viết."""

from typing import Any

from pydantic import BaseModel, field_validator

from src.ai.shared.text_coercion import to_text


class ContractClauses(BaseModel):
    """CHỈ những điều khoản văn xuôi mà AI được phép viết.

    Cố ý KHÔNG có ``parties`` và ``governing_law``:

    - ``parties`` là danh tính pháp lý của hai bên ký. Dữ liệu này đã có sẵn trong
      DB (client_data, user_profile) nên code gán thẳng. Để model tự sinh thì chỉ
      cần nó bịa sai một chữ trong email hay tên khách là ta có một hợp đồng SAI
      CHỦ THỂ. Không phải lo xa: chính con llama này từng trả `pricing` lúc là
      chuỗi lúc là object — model bịa được số tiền thì bịa được tên người.
    - ``governing_law`` luôn là "Vietnam" theo contracts/openapi.yaml (default).

    Ghép đủ 8 trường của ContractContentDTO ở chain.py.  #Huynh
    """

    scope_of_work: str

    payment_terms: str

    revision_policy: str

    ip_ownership: str

    termination_clause: str

    custom_clauses: str = ""

    # Prompt yêu cầu trả chuỗi, nhưng llama-4-scout hay "sáng tạo" thành mảng gạch
    # đầu dòng hoặc object. Ép kiểu ở đây thay vì để pydantic ném ValidationError
    # rồi endpoint 500 — đúng cách proposal_generator đang xử lý.  #Huynh
    @field_validator(
        "scope_of_work",
        "payment_terms",
        "revision_policy",
        "ip_ownership",
        "termination_clause",
        "custom_clauses",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return to_text(value)


def build_parties(
    client_data: dict[str, Any],
    user_profile: dict[str, Any],
) -> dict[str, Any]:
    """Dựng ``parties`` từ dữ liệu DB — không hỏi AI.

    Khớp ContractPartiesDTO trong contracts/openapi.yaml.  #Huynh
    """
    return {
        "freelancer": {
            "name": to_text(user_profile.get("name")),
            "email": to_text(user_profile.get("email")),
            "business_name": to_text(user_profile.get("business_name")),
        },
        "client": {
            "name": to_text(client_data.get("name")),
            "email": to_text(client_data.get("email")),
            "address": to_text(client_data.get("address")),
        },
    }
