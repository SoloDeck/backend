"""Render TỜ GIẤY THẬT từ nội dung một mẫu, cho admin soạn mà nhìn thấy ngay kết quả.

Trước bản này admin soạn mẫu trong một form toàn ô chữ, còn tờ báo giá/hợp đồng thật thì chỉ
freelancer mới thấy. Nghĩa là người soạn ra nội dung gửi khách hàng chưa từng nhìn thấy nội
dung đó nằm trên giấy — không biết mục mình gõ rơi vào đâu, dài ngắn thế nào, có bị nuốt mất
vì rỗng hay không.

Đường này KHÁC hẳn `_build_document` bên proposals/contracts: ở đó tài liệu dựng từ một bản
ghi CÓ THẬT trong DB (deal, khách, giá). Ở đây chưa có gì cả — chỉ có nội dung mẫu — nên phần
danh tính hai bên và tiền được thay bằng chữ giữ chỗ, ghi rõ trong ngoặc để không ai nhầm nó
là dữ liệu thật.

Luôn render ở chế độ `editable=True`: đây là màn SOẠN, mọi mục phải hiện ra kể cả khi trống,
bằng không admin không có chỗ bấm vào để nhập.  #Huynh
"""

from datetime import UTC, date, datetime, timedelta

from src.ai.contract_generator.application.render import ContractPdfRenderer
from src.ai.contract_generator.schemas.contract_document import ContractDocument
from src.ai.proposal_generator.application.render import ProposalPdfRenderer
from src.ai.proposal_generator.schemas.proposal_document import ProposalDocument
from src.shared.domain.template_blocks import (
    CLAUSE_TEXTS_KEY,
    EXTRA_SECTIONS_KEY,
    HIDDEN_SECTIONS_KEY,
    LEGACY_BODY_KEY,
    SECTION_TITLES_KEY,
    VALID_DAYS_KEY,
    build_skeleton_content,
    collect_clause_texts,
    collect_extra_sections,
    collect_hidden_sections,
    collect_section_titles,
)

# Chữ giữ chỗ cho phần KHÔNG thuộc về mẫu: danh tính hai bên và tiền đều do freelancer/khách
# quyết theo từng dự án. Để trong ngoặc đơn cho khác hẳn nội dung thật — admin nhìn là biết
# ngay đâu là chỗ mình soạn, đâu là chỗ hệ thống điền sau.
_CHO_TEN_FREELANCER = "(Tên freelancer)"
_CHO_TEN_KHACH = "(Tên khách hàng)"
_CHO_LOAI_DU_AN = "(Loại dự án)"
_CHO_TIEN = "(Chi phí do freelancer nhập cho từng dự án)"


def _lines(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(_lines(value))
    return str(value or "").strip()


def _vn_date(value: date) -> str:
    return f"ngày {value.day:02d} tháng {value.month:02d} năm {value.year}"


def _valid_until(content: dict) -> str:
    """Hạn hiệu lực suy từ `valid_days` của mẫu, tính từ hôm nay.

    Mẫu chỉ gợi ý SỐ NGÀY; ngày cụ thể phụ thuộc lúc freelancer gửi. Preview lấy hôm nay làm
    mốc để admin thấy được con số mình đặt trông ra sao trên giấy.
    """
    raw = content.get(VALID_DAYS_KEY)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return ""
    if days <= 0:
        return ""
    return _vn_date(datetime.now(UTC).date() + timedelta(days=days))


def _proposal_document(content: dict) -> ProposalDocument:
    today = datetime.now(UTC).date()
    return ProposalDocument(
        freelancer_name=_CHO_TEN_FREELANCER,
        client_name=_CHO_TEN_KHACH,
        project_type=_CHO_LOAI_DU_AN,
        proposal_date=_vn_date(today),
        valid_until=_valid_until(content),
        project_overview=_text(content.get("project_overview")),
        scope_of_work=_lines(content.get("scope_of_work")),
        deliverables=_lines(content.get("deliverables")),
        timeline=_text(content.get("timeline")),
        # Mẫu TUYỆT ĐỐI không chạm tiền, nên chỗ này luôn là chữ giữ chỗ — và đó cũng là cách
        # nói cho admin biết mục 7 không phải việc của họ.
        pricing=_CHO_TIEN,
        payment_terms=_text(content.get("payment_terms")),
        assumptions=_text(content.get("assumptions")),
        out_of_scope=_lines(content.get("out_of_scope")),
        revision_policy=_text(content.get("revision_policy")),
        standard_terms=_text(content.get("standard_terms")) or _text(content.get(LEGACY_BODY_KEY)),
        # `keep_untitled`: mục vừa thêm chưa có tên vẫn phải hiện, bằng không admin
        # không có chỗ nào để gõ tên vào.
        extra_sections=collect_extra_sections(content, keep_untitled=True),
        section_titles=collect_section_titles(content, "proposal"),
        clause_texts=collect_clause_texts(content, "proposal"),
        hidden_sections=collect_hidden_sections(content, "proposal"),
    )


def _contract_document(content: dict) -> ContractDocument:
    today = datetime.now(UTC).date()
    return ContractDocument(
        contract_number="HD-XXXX-000",
        contract_date=_vn_date(today),
        freelancer_name=_CHO_TEN_FREELANCER,
        client_name=_CHO_TEN_KHACH,
        scope_of_work=_text(content.get("scope_of_work")),
        payment_terms=_text(content.get("payment_terms")),
        revision_policy=_text(content.get("revision_policy")),
        ip_ownership=_text(content.get("ip_ownership")),
        termination_clause=_text(content.get("termination_clause")),
        custom_clauses=_text(content.get("custom_clauses")),
        standard_terms=_text(content.get("standard_terms")) or _text(content.get(LEGACY_BODY_KEY)),
        # `keep_untitled`: mục vừa thêm chưa có tên vẫn phải hiện, bằng không admin
        # không có chỗ nào để gõ tên vào.
        extra_sections=collect_extra_sections(content, keep_untitled=True),
        section_titles=collect_section_titles(content, "contract"),
        clause_texts=collect_clause_texts(content, "contract"),
        hidden_sections=collect_hidden_sections(content, "contract"),
    )


def render_template_preview(template_type: str, content: dict) -> str:
    """HTML tờ giấy dựng từ nội dung mẫu, ở chế độ sửa tại chỗ.

    Đi qua `build_skeleton_content` trước để CHỈ những khoá mẫu được phép chứa mới tới được
    trang giấy. Không có bước này thì màn soạn của admin trở thành một lối vòng để nhét khoá
    tuỳ ý (kể cả khoá TIỀN) vào tài liệu — đúng bất biến mà cả cổng gửi báo giá lẫn bộ sinh
    task thu tiền đang dựa vào.  #Huynh
    """
    goc = content if isinstance(content, dict) else {}
    sach = build_skeleton_content(goc, template_type)
    # `valid_days` là con số, không thuộc bảng khối nên `build_skeleton_content` không giữ.
    if VALID_DAYS_KEY in goc:
        sach[VALID_DAYS_KEY] = goc[VALID_DAYS_KEY]
    # Đầu mục lấy từ BẢN GỐC chứ không lấy bản đã lọc: `build_skeleton_content` bỏ mục chưa đặt
    # tên (đúng cho bản gửi khách), nhưng ở màn soạn thì mục vừa thêm chưa có tên vẫn phải hiện,
    # bằng không admin không có chỗ nào để gõ tên vào.
    if EXTRA_SECTIONS_KEY in goc:
        sach[EXTRA_SECTIONS_KEY] = goc[EXTRA_SECTIONS_KEY]
    if SECTION_TITLES_KEY in goc:
        sach[SECTION_TITLES_KEY] = goc[SECTION_TITLES_KEY]
    if CLAUSE_TEXTS_KEY in goc:
        sach[CLAUSE_TEXTS_KEY] = goc[CLAUSE_TEXTS_KEY]
    if HIDDEN_SECTIONS_KEY in goc:
        sach[HIDDEN_SECTIONS_KEY] = goc[HIDDEN_SECTIONS_KEY]

    if template_type == "contract":
        return ContractPdfRenderer().render_html(_contract_document(sach), editable=True)
    return ProposalPdfRenderer().render_html(_proposal_document(sach), editable=True)
