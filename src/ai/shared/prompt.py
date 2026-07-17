"""Nạp prompt cho mọi module AI — MỘT chỗ duy nhất.

Trước đây mỗi module tự nạp một kiểu: `lead_qualifier` đọc trong `chain.py`,
`proposal_generator` đọc tận trong `application/service.py`. Tên file cũng không thống
nhất — hai module đọc `prompts.txt`, hai module đọc `system.txt`. Và có hai file
`system.txt` chỉ chứa đúng dòng ``# TODO: add system-level instructions here`` mà KHÔNG
ai đọc: người mới vào nhóm sửa đúng file đó rồi ngồi thắc mắc sao AI không đổi hành vi.

Quy ước từ nay:

    src/ai/<module>/prompts/system.txt      <- MỘT file, MỘT tên, không có ngoại lệ

VÌ SAO CẦN PHIÊN BẢN PROMPT:

Sửa prompt là ĐỔI HÀNH VI AI. Deal chấm hôm qua bằng prompt cũ, hôm nay prompt mới — hai
kết quả khác nhau trên cùng một dữ liệu, và không ai truy ngược được vì sao. Băm nội dung
prompt rồi ghi kèm kết quả thì luôn trả lời được "bản ghi này sinh ra bởi prompt nào".

Băm nội dung thay vì đánh số tay: đánh số tay thì kiểu gì cũng có ngày sửa prompt mà quên
tăng số, và lúc đó con số còn tệ hơn không có.  #Huynh
"""

import hashlib
from functools import lru_cache
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=8)
def load_prompt(module: str) -> str:
    """Đọc ``src/ai/<module>/prompts/system.txt``.

    Cache vì prompt không đổi trong một tiến trình — đọc đĩa mỗi lần gọi AI là phí.
    Đổi prompt thì phải khởi động lại tiến trình (worker KHÔNG tự nạp lại như api).
    """
    path = AI_ROOT / module / "prompts" / "system.txt"
    if not path.is_file():
        raise FileNotFoundError(
            f"Thiếu prompt cho module AI '{module}'. Phải có file: {path}"
        )

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Prompt của module '{module}' rỗng: {path}")

    return content


@lru_cache(maxsize=8)
def prompt_version(module: str) -> str:
    """8 ký tự đầu của SHA-256 nội dung prompt — ví dụ ``a3f9c21b``.

    Ghi kèm mọi kết quả AI. Prompt đổi một chữ là mã này đổi.
    """
    return hashlib.sha256(load_prompt(module).encode("utf-8")).hexdigest()[:8]
