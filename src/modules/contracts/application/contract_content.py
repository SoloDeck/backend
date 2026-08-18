"""Chuyển ContractModel + nội dung AI thành ContractDocument để render HTML/PDF.

Song song với ``proposals/application/pdf_content.py``. ``content`` là JSONB trần nên
dùng ``.get()`` khắp nơi — thiếu khoá thì để trống chứ không nổ.

Danh tính hai bên ƯU TIÊN dữ liệu sống trong DB (user/client) rồi mới tới ``parties``
mà AI đã ghi vào content: nếu model có lỡ bịa sai một chữ trong tên/email thì bản render
vẫn lấy đúng thứ trong bảng users/clients. Số điện thoại, địa chỉ chỉ có trong DB, AI
không thấy.  #Huynh
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from src.ai.contract_generator.schemas.contract_document import (
    ContractDocument,
    ContractMilestoneLine,
)
from src.shared.domain.template_blocks import (
    collect_clause_texts,
    collect_extra_sections,
    collect_hidden_sections,
    collect_section_titles,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _money(amount: Any) -> str:
    """Định dạng tiền kiểu Việt Nam: 30.000.000 VND.  #Huynh"""
    try:
        return f"{int(Decimal(str(amount))):,}".replace(",", ".") + " VND"
    except (TypeError, ValueError, InvalidOperation):
        return _text(amount)


def _vn_date(value: Any) -> str:
    """Ngày kiểu Việt: 31/07/2026. Rác thì trả rỗng.  #Huynh"""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_contract_document(
    contract: Any,
    *,
    deal: Any = None,
    client: Any = None,
    user: Any = None,
    milestones: list[Any] | None = None,
) -> ContractDocument:
    """Dựng ContractDocument từ một ContractModel + các thực thể liên quan.  #Huynh"""
    content = _dict(getattr(contract, "content", None))
    parties = _dict(content.get("parties"))
    p_free = _dict(parties.get("freelancer"))
    p_client = _dict(parties.get("client"))
    snapshot = _dict(getattr(contract, "client_snapshot", None))

    # Ngày lập neo vào sự thật đã lưu: ưu tiên effective_date, chưa có thì ngày tạo hợp
    # đồng. KHÔNG lấy "hôm nay" — mở lại hợp đồng cũ mà thấy ngày ký nhảy sang hôm nay là
    # thứ khiến giấy tờ mất tin cậy.  #Huynh
    created = getattr(contract, "created_at", None)
    issued = getattr(contract, "effective_date", None) or (
        created.date() if isinstance(created, datetime) else None
    )
    version_number = getattr(contract, "version_number", None) or 1
    contract_number = f"HD-{issued.year}-{version_number:03d}" if issued else ""

    # --- BÊN A (freelancer) ---
    freelancer_name = _text(getattr(user, "full_name", "")) or _text(p_free.get("name"))
    freelancer_business = _text(getattr(user, "business_name", "")) or _text(
        p_free.get("business_name")
    )
    freelancer_email = _text(getattr(user, "email", "")) or _text(p_free.get("email"))
    freelancer_phone = _text(getattr(user, "phone", ""))

    # --- BÊN B (khách hàng) ---
    client_name = (
        _text(getattr(client, "name", ""))
        or _text(snapshot.get("name"))
        or _text(p_client.get("name"))
    )
    client_company = client_name if getattr(client, "type", None) == "company" else ""
    client_email = (
        _text(getattr(client, "email", ""))
        or _text(snapshot.get("email"))
        or _text(p_client.get("email"))
    )
    client_phone = _text(getattr(client, "phone", "")) or _text(snapshot.get("phone"))
    client_address = ", ".join(
        part
        for part in (
            _text(getattr(client, "address_city", "")),
            _text(getattr(client, "address_country", "")),
        )
        if part
    ) or _text(p_client.get("address"))

    # --- Lịch thanh toán ---
    lines: list[ContractMilestoneLine] = []
    total = Decimal(0)
    for m in milestones or []:
        amount = getattr(m, "amount", None)
        try:
            total += Decimal(str(amount))
        except (TypeError, ValueError, InvalidOperation):
            pass
        lines.append(
            ContractMilestoneLine(
                description=_text(getattr(m, "description", "")),
                amount=_money(amount),
                due_date=_vn_date(getattr(m, "due_date", None)),
            )
        )
    total_amount = _money(total) if lines else ""

    # governing_law lưu trong DB là "Vietnam" (theo openapi.yaml). Hiển thị cho khách VN
    # thì viết đúng tiếng Việt.  #Huynh
    governing_law = _text(content.get("governing_law"))
    if governing_law.lower() in ("vietnam", "viet nam", "việt nam", ""):
        governing_law = "Việt Nam"

    project_name = _text(getattr(deal, "project_type", "")) or _text(getattr(deal, "title", ""))

    return ContractDocument(
        project_name=project_name,
        contract_number=contract_number,
        contract_date=_vn_date(issued),
        proposal_reference="Báo giá đã được Bên B chấp nhận (đính kèm Phụ lục A)",
        freelancer_name=freelancer_name,
        freelancer_business_name=freelancer_business,
        freelancer_email=freelancer_email,
        freelancer_phone=freelancer_phone,
        client_name=client_name,
        client_company=client_company,
        client_email=client_email,
        client_phone=client_phone,
        client_address=client_address,
        scope_of_work=_text(content.get("scope_of_work")),
        payment_terms=_text(content.get("payment_terms")),
        revision_policy=_text(content.get("revision_policy")),
        ip_ownership=_text(content.get("ip_ownership")),
        termination_clause=_text(content.get("termination_clause")),
        governing_law=governing_law,
        custom_clauses=_text(content.get("custom_clauses")),
        standard_terms=_text(content.get("standard_terms")),
        # Đầu mục do admin tự soạn trong mẫu. Đi qua `collect_extra_sections` để mục không có
        # tiêu đề bị loại — mục không tên in ra thành `<h2>9. </h2>`, số nhảy mà đầu đề trống.
        extra_sections=collect_extra_sections(content),
        section_titles=collect_section_titles(content, "contract"),
        clause_texts=collect_clause_texts(content, "contract"),
        hidden_sections=collect_hidden_sections(content, "contract"),
        milestones=lines,
        total_amount=total_amount,
        effective_date=_vn_date(getattr(contract, "effective_date", None)),
        end_date=_vn_date(getattr(contract, "end_date", None)),
        version_number=version_number,
    )
