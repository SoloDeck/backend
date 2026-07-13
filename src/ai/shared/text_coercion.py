"""Ép dữ liệu model trả về thành văn bản.

llama-4-scout không giữ đúng kiểu mà prompt yêu cầu: chỗ đáng lẽ là chuỗi thì
thỉnh thoảng nó trả về object hoặc mảng. Cùng một request, lần được lần không.
Thay vì tin model, các schema AI ép kiểu ở tầng validator bằng mấy hàm dưới đây.

Trước đây phần này nằm riêng trong proposal_generator; contract_generator cũng cần
đúng như vậy nên tôi chuyển ra dùng chung, tránh cảnh sửa nơi này quên nơi kia —
giống lý do đã tách ``extract_json_object``.  #Huynh
"""

from typing import Any


def to_text(value: Any) -> str:
    """Ép mọi thứ model trả về thành văn bản đọc được.  #Huynh"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(to_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {to_text(val)}" for key, val in value.items())
    return str(value)


def to_text_list(value: Any) -> list[str]:
    """Ép mọi thứ model trả về thành danh sách chuỗi.  #Huynh"""
    if value is None:
        return []
    if isinstance(value, list):
        return [to_text(item) for item in value]
    if isinstance(value, dict):
        return [f"{key}: {to_text(val)}" for key, val in value.items()]
    return [to_text(value)]
