"""Chuyển `proposal.content` (JSONB) thành ProposalDocument để render PDF.

Vì sao cần file này: `content` được khai là `dict` trần nên backend KHÔNG validate
gì cả, và thực tế đang có HAI shape cùng tồn tại trong DB:

1. **ProposalContentDTO** — shape CHÍNH THỨC trong `contracts/openapi.yaml`, và là
   thứ frontend lưu mỗi khi người dùng sửa báo giá:
   ``{title, executive_summary, scope_of_work: str, timeline: {...}, pricing: {...},
   terms: {payment_terms}, notes}``

2. **Shape nội bộ của AI** — `/proposals/ai-generate` lưu thẳng output của model:
   ``{project_overview, scope_of_work: list, deliverables, timeline: str,
   pricing: str, payment_terms, assumptions}``

Bản cũ của `generate_pdf` index cứng bằng ``content["project_overview"]`` — tức là
chỉ đọc được shape (2), và dùng ``[...]`` chứ không ``.get()`` nên thiếu MỘT khoá là
`KeyError` → **500**. Kết quả: mọi báo giá do frontend tạo/sửa đều không xuất được
PDF, dù frontend làm ĐÚNG hợp đồng.

Ở đây ta đọc được cả hai, ưu tiên shape của hợp đồng, và dùng `.get()` khắp nơi để
thiếu dữ liệu thì để trống chứ không nổ.  #Huynh
"""

from typing import Any

from src.ai.proposal_generator.schemas.proposal_document import ProposalDocument


def _text(value: Any) -> str:
    """Ép về chuỗi; None thành rỗng.  #Huynh"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _text_list(value: Any) -> list[str]:
    """Ép về danh sách chuỗi.

    `scope_of_work` là `list` ở shape AI nhưng là `str` (nhiều dòng) ở shape hợp
    đồng — nên phải nhận cả hai.  #Huynh
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [_text(value)]


def _money(amount: Any, currency: str) -> str:
    """Định dạng tiền theo kiểu Việt Nam: 30.000.000 VND.  #Huynh"""
    try:
        return f"{int(float(amount)):,}".replace(",", ".") + (f" {currency}" if currency else "")
    except (TypeError, ValueError):
        return _text(amount)


def _pricing_to_text(value: Any) -> str:
    """Shape hợp đồng cho `pricing` là object; shape AI là chuỗi. Nhận cả hai.  #Huynh"""
    if not isinstance(value, dict):
        return _text(value)

    currency = _text(value.get("currency")) or "VND"
    lines: list[str] = []

    for item in value.get("line_items") or []:
        if not isinstance(item, dict):
            lines.append(_text(item))
            continue
        desc = _text(item.get("description"))
        amount = item.get("amount")
        lines.append(f"{desc}: {_money(amount, currency)}" if amount is not None else desc)

    total = value.get("total")
    if total is not None:
        lines.append(f"Tổng cộng: {_money(total, currency)}")

    return "\n".join(line for line in lines if line)


def _timeline_to_text(value: Any) -> str:
    """Shape hợp đồng cho `timeline` là object (mốc thời gian); shape AI là chuỗi.  #Huynh"""
    if not isinstance(value, dict):
        return _text(value)

    lines: list[str] = []
    start, end = _text(value.get("start_date")), _text(value.get("end_date"))
    if start or end:
        lines.append(" – ".join(part for part in (start, end) if part))

    for milestone in value.get("milestones") or []:
        if not isinstance(milestone, dict):
            lines.append(_text(milestone))
            continue
        title = _text(milestone.get("title"))
        due = _text(milestone.get("due_date"))
        lines.append(f"{title} ({due})" if title and due else title or due)

    return "\n".join(line for line in lines if line)


def build_proposal_document(
    content: dict[str, Any],
    *,
    freelancer_name: str,
    client_name: str,
    company_name: str | None,
    project_type: str,
    proposal_date: str,
) -> ProposalDocument:
    """Dựng ProposalDocument từ `content` bất kể nó theo shape nào.  #Huynh"""
    content = content or {}

    # Ưu tiên shape của hợp đồng (executive_summary), rồi mới tới shape AI
    # (project_overview), cuối cùng là title.
    overview = (
        _text(content.get("executive_summary"))
        or _text(content.get("project_overview"))
        or _text(content.get("title"))
    )

    raw_terms = content.get("terms")
    terms: dict[str, Any] = raw_terms if isinstance(raw_terms, dict) else {}
    payment_terms = _text(content.get("payment_terms")) or _text(terms.get("payment_terms"))

    # `notes` (hợp đồng) và `assumptions` (AI) đóng cùng vai trò: ghi chú thêm.
    assumptions = _text(content.get("assumptions")) or _text(content.get("notes"))

    return ProposalDocument(
        freelancer_name=freelancer_name,
        client_name=client_name,
        company_name=company_name,
        project_type=project_type,
        proposal_date=proposal_date,
        project_overview=overview,
        scope_of_work=_text_list(content.get("scope_of_work")),
        deliverables=_text_list(content.get("deliverables")),
        timeline=_timeline_to_text(content.get("timeline")),
        pricing=_pricing_to_text(content.get("pricing")),
        payment_terms=payment_terms,
        assumptions=assumptions,
    )
