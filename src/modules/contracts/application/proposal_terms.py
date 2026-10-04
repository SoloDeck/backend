"""Phần hợp đồng LẤY TỪ BÁO GIÁ ĐÃ CHỐT — bằng code, không qua AI.

Hai chỗ lệch đã đo được khi thử trọn flow (báo giá -> hợp đồng -> ký):

- Đường KHÔNG AI: hợp đồng chỉ lấy chữ từ mẫu, không đọc báo giá. Điều 1 chỉ một câu chung, Điều 3
  không có tổng giá trị lẫn lịch thanh toán — tờ hợp đồng ký xong mà không ghi số tiền nào.
- Đường CÓ AI: model tự viết lại các đợt thanh toán, nên số từng đợt lệch bảng hạng mục của báo
  giá (2,4 / 3,6 / 4,8 / 1,2 triệu so với 3,6 / 1,615 / 2,585 / 3,392 / 0,808 triệu). Tổng cùng 12
  triệu nhưng từng đợt khác — trong khi task thu tiền và hoá đơn lại bám đúng báo giá.

Cả hai cùng một cách chữa: tiền do CODE đọc từ `resolve_cost_items` — đúng nguồn mà bảng báo giá, bộ
sinh task thu tiền và hoá đơn đang dùng — nên bốn nơi không thể hiểu khác nhau về "hạng mục là gì,
bao nhiêu tiền". AI vẫn viết phần văn xuôi (phạm vi, chỉnh sửa, sở hữu trí tuệ...), chỉ không được
đụng tới con số.  #Huynh
"""

import re
from typing import Any

from src.ai.contract_generator.schemas.contract_document import ContractMilestoneLine
from src.modules.proposals.application.pdf_content import CostItem, resolve_cost_items
from src.shared.domain.vn_number import vnd_in_words

_BULLET_PREFIX = re.compile(r"^\s*[-•*]+\s*")

PAYMENT_METHOD_SENTENCE = (
    "Hình thức thanh toán: chuyển khoản ngân hàng hoặc hình thức khác do hai Bên thống nhất bằng "
    "văn bản."
)


def _money(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", ".") + (f" {currency}" if currency else "")


def cost_items_of(proposal_content: dict[str, Any] | None) -> list[CostItem]:
    return resolve_cost_items(proposal_content or {})


def schedule_from_proposal(
    proposal_content: dict[str, Any] | None,
) -> tuple[list[ContractMilestoneLine], str]:
    """Bảng lịch thanh toán + tổng giá trị, dựng từ hạng mục chi phí của báo giá.

    Cột "Hạn" lấy thời điểm thu của từng hạng mục ("Khi ký hợp đồng", "Khi hoàn thành hạng mục" hay
    ghi chú riêng) — hạng mục chưa có ngày cụ thể nên in cái mốc đã thoả thuận thay vì để trống.
    Báo giá không có hạng mục nào thì trả rỗng: không bịa ra một bảng.
    """
    items = cost_items_of(proposal_content)
    if not items:
        return [], ""

    currency = items[0].currency
    lines = [
        ContractMilestoneLine(
            description=item.label,
            amount=_money(item.amount, item.currency),
            due_date=item.due_label,
        )
        for item in items
    ]
    return lines, _money(sum(item.amount for item in items), currency)


def payment_terms_from_proposal(proposal_content: dict[str, Any] | None) -> str:
    """Câu mở đầu Điều "Giá trị hợp đồng và thanh toán": tổng tiền bằng số và bằng chữ."""
    items = cost_items_of(proposal_content)
    if not items:
        return ""

    currency = items[0].currency
    total = sum(item.amount for item in items)
    # Bằng chữ chỉ đọc được cho đồng Việt Nam; ngoại tệ thì chỉ ghi số, đừng bịa cách đọc.
    words = vnd_in_words(total) if currency == "VND" else ""
    total_text = _money(total, currency) + (f" ({words})" if words else "")
    return (
        f"Tổng giá trị hợp đồng là {total_text}. Bên B thanh toán cho Bên A theo các đợt trong "
        "bảng dưới đây; mỗi hạng mục được xuất hoá đơn riêng khi đến thời điểm thu đã ghi. "
        f"{PAYMENT_METHOD_SENTENCE}"
    )


def apply_payment_from_proposal(
    content: dict[str, Any],
    proposal_content: dict[str, Any] | None,
    *,
    replace_text: bool,
) -> dict[str, Any]:
    """Gắn câu về tổng giá trị vào `payment_terms`.

    `replace_text=True` (đường AI): bỏ hẳn đoạn model viết — nó chứa các con số tự soạn.
    `replace_text=False` (đường mẫu): giữ lời admin viết trong mẫu và đặt câu về tiền lên TRƯỚC, vì
    mẫu là văn bản chung cho cả nghề, không thể biết số tiền của từng dự án.
    """
    intro = payment_terms_from_proposal(proposal_content)
    if not intro:
        return content

    out = dict(content)
    existing = str(out.get("payment_terms") or "").strip()
    out["payment_terms"] = intro if replace_text or not existing else f"{intro}\n{existing}"
    return out


def _as_lines(value: Any) -> list[str]:
    """`scope_of_work` là danh sách ở báo giá nhưng có thể là đoạn nhiều dòng ở dữ liệu cũ."""
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).splitlines()
    cleaned = (_BULLET_PREFIX.sub("", str(item)).strip() for item in raw)
    return [line for line in cleaned if line]


def scope_from_proposal(proposal_content: dict[str, Any] | None) -> str:
    """Điều 1 dựng từ báo giá: phạm vi công việc, sản phẩm bàn giao, phạm vi không bao gồm.

    Cùng khuôn với đoạn AI vẫn viết ("1. Phạm vi công việc: / - ..."), để hai đường ra tờ giấy giống
    nhau. Mục nào báo giá không có thì bỏ, số thứ tự đánh lại cho liền mạch.
    """
    content = proposal_content or {}
    sections = (
        ("Phạm vi công việc", _as_lines(content.get("scope_of_work"))),
        ("Sản phẩm bàn giao", _as_lines(content.get("deliverables"))),
        ("Phạm vi không bao gồm", _as_lines(content.get("out_of_scope"))),
    )
    blocks: list[str] = []
    for title, lines in sections:
        if not lines:
            continue
        number = len(blocks) + 1
        bullets = "\n".join(f"- {line}" for line in lines)
        blocks.append(f"{number}. {title}:\n{bullets}")
    return "\n".join(blocks)


def apply_scope_from_proposal(
    content: dict[str, Any], proposal_content: dict[str, Any] | None
) -> dict[str, Any]:
    """Đặt phạm vi công việc của báo giá vào Điều 1, sau câu dẫn (nếu có) của mẫu."""
    scope = scope_from_proposal(proposal_content)
    if not scope:
        return content

    out = dict(content)
    lead = str(out.get("scope_of_work") or "").strip()
    out["scope_of_work"] = f"{lead}\n{scope}" if lead else scope
    return out
