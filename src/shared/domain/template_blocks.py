"""Mẫu điều khoản của admin gồm những KHỐI nào — nguồn sự thật duy nhất.

Một "mẫu" trước đây là MỘT đoạn văn (`content = {"body": "..."}`) đổ vào MỘT khoá
(`standard_terms`), render thành MỘT mục ở gần cuối tờ giấy. Chín mục đầu vẫn 100% do AI viết,
nên freelancer chọn mẫu xong gần như không thấy gì khác — nhìn từ ngoài thì như chưa làm.

Nay mẫu gồm nhiều khối CÓ TÊN. Bảng khoá đặt ở đây, dùng chung cho cả hai module, để hai bên
không bao giờ hiểu khác nhau về "mẫu chứa được gì". Đây là HẰNG SỐ thuần, không phải lời gọi
chéo repository — vẫn đúng luật tách module.

Một mẫu phục vụ HAI chế độ soạn, và mỗi chế độ lấy một bộ khoá khác nhau:

* **Chế độ AI** — AI viết cả tờ, mẫu chạy SAU và chép đè vài khối. Bộ khoá hẹp
  (`*_TEMPLATE_BLOCKS`).
* **Chế độ khung** — freelancer không nhờ AI, mẫu là NỀN của cả tờ giấy. Bộ khoá rộng
  (`*_SKELETON_BLOCKS`), gồm cả phần đặc thù dự án.

BA NGUYÊN TẮC KHÔNG ĐƯỢC PHÁ:

1. **Mẫu tuyệt đối không chạm tiền — ở CẢ HAI chế độ.** Không `pricing*`, không `pricing_items`,
   không `milestones`, không `total_amount`. Ba nơi — cổng gửi báo giá, `resolve_cost_items`, bộ
   sinh task thu tiền — đang cùng dựa trên bất biến "tổng hạng mục = giá chào khách". Cho admin
   ghi đè tiền từ một mẫu dùng chung là phá bất biến đó từ bên ngoài.

2. **Chế độ AI không chạm phần đặc thù dự án.** Tổng quan, phạm vi công việc, sản phẩm bàn giao,
   tiến độ — ở chế độ AI đó là việc của AI vì nó vừa đọc yêu cầu THẬT của khách, mẫu chép đè lên
   là xoá mất đúng phần đáng giá nhất. Ở chế độ khung thì ngược lại: không có AI, nên mẫu PHẢI
   với được tới các mục đó, bằng không tờ giấy chỉ có điều khoản mà không có nội dung. Vì vậy
   hai bộ khoá TÁCH RIÊNG, không nới bộ này thành bộ kia.

3. **Khoá nào không có trong bảng này thì bị bỏ qua.** Admin nhét khoá lạ vào `content` cũng
   không đi tới đâu — danh sách cho phép, không phải danh sách cấm.  #Huynh
"""

# Nhãn tiếng Việt hiện trong bộ chọn mẫu, để freelancer biết mẫu này điền những gì.
PROPOSAL_TEMPLATE_BLOCKS: dict[str, str] = {
    # Chống scope creep — gần như cố định theo nghề. Mảng chuỗi, mỗi phần tử một gạch đầu dòng.
    "out_of_scope": "Ngoài phạm vi",
    # AI KHÔNG hề sinh trường này (không có trong schema đầu ra), nên trước nay luôn trống trừ
    # khi freelancer tự gõ. Đúng thứ đáng làm mẫu.
    "revision_policy": "Chính sách chỉnh sửa",
    "standard_terms": "Điều khoản chuẩn",
}

CONTRACT_TEMPLATE_BLOCKS: dict[str, str] = {
    # Khác hẳn nhau giữa các nghề: ảnh/video bàn giao quyền dùng, lập trình bàn giao mã nguồn.
    "ip_ownership": "Quyền sở hữu trí tuệ",
    "termination_clause": "Sửa đổi và chấm dứt",
    "standard_terms": "Điều khoản chuẩn",
    "custom_clauses": "Điều khoản bổ sung",
}

# ---------------------------------------------------------------------------
# Chế độ KHUNG: mẫu là nền của cả tờ giấy, không có AI nào viết hộ.
#
# Xếp theo ĐÚNG thứ tự các mục hiện trên tờ giấy, để form của admin đọc từ trên xuống là khớp
# với thứ tự freelancer sẽ nhìn thấy.
#
# Khối nào admin để trống thì KHÔNG có chữ nào được bịa ra thay — mục đó ra một ô rỗng bấm sửa
# được (xem cờ `editable` của hai template). Đặt sẵn văn bản mồi trong code là biến một quyết
# định nghiệp vụ của admin thành hằng số lập trình.  #Huynh
# ---------------------------------------------------------------------------
PROPOSAL_SKELETON_BLOCKS: dict[str, str] = {
    "project_overview": "Tổng quan dự án",
    "scope_of_work": "Phạm vi công việc",
    "deliverables": "Sản phẩm bàn giao",
    "timeline": "Thời gian thực hiện",
    "payment_terms": "Điều khoản thanh toán",
    "out_of_scope": "Ngoài phạm vi",
    "revision_policy": "Chính sách chỉnh sửa",
    "assumptions": "Ghi chú và giả định",
    "standard_terms": "Điều khoản chuẩn",
}

CONTRACT_SKELETON_BLOCKS: dict[str, str] = {
    "scope_of_work": "Nội dung và phạm vi công việc",
    "payment_terms": "Giá trị hợp đồng và thanh toán",
    "ip_ownership": "Quyền sở hữu trí tuệ",
    "termination_clause": "Sửa đổi và chấm dứt",
    "revision_policy": "Chính sách chỉnh sửa và phát sinh",
    "standard_terms": "Điều khoản chuẩn",
    "custom_clauses": "Điều khoản bổ sung",
}

# Khoá nhận MẢNG chuỗi thay vì một chuỗi. Chế độ AI chỉ có một khoá như vậy, và nó thuộc về báo
# giá — hợp đồng không có khoá mảng nào nên một tập dùng chung là đủ.
LIST_BLOCKS: frozenset[str] = frozenset({"out_of_scope"})

# Chế độ khung thì tính-mảng KHÁC NHAU giữa hai loại tài liệu: `scope_of_work` là danh sách gạch
# đầu dòng trên tờ báo giá (`<ul data-field="scope_of_work">`) nhưng là một đoạn văn trong Điều 1
# của hợp đồng (`<p data-field="scope_of_work">`). Dùng chung một tập là ra mảng in vào chỗ chờ
# chuỗi.  #Huynh
PROPOSAL_SKELETON_LIST_BLOCKS: frozenset[str] = frozenset(
    {"scope_of_work", "deliverables", "out_of_scope"}
)
CONTRACT_SKELETON_LIST_BLOCKS: frozenset[str] = frozenset()

# Không khoá nào trong đây được phép lọt vào BẤT KỲ bộ khối nào. Có hằng số này để bài test kẹp
# được nguyên tắc 1 thành một khẳng định máy kiểm tra được, thay vì một dòng chú thích.
MONEY_KEYS: frozenset[str] = frozenset(
    {
        "pricing",
        "pricing_detail",
        "pricing_items",
        "pricing_line_items",
        "payment_milestones",
        "milestones",
        "total_amount",
        "final_price",
    }
)

# Số ngày hiệu lực báo giá do mẫu gợi ý. Không nằm trong bảng khối vì nó là một CON SỐ và đi
# vào `valid_until` (một ngày cụ thể) chứ không phải một khối văn bản.
VALID_DAYS_KEY = "valid_days"

# Khoá của bản CŨ: một đoạn văn duy nhất. Bốn mẫu admin đã nhập đang dùng nó, nên phải đọc tiếp
# như bí danh của `standard_terms` — nâng cấp cấu trúc không được làm hỏng dữ liệu người ta gõ.
LEGACY_BODY_KEY = "body"

# Đầu mục do ADMIN tự đặt tên. Không nằm trong bảng khối vì nó không phải MỘT khoá cố định —
# nó là một DANH SÁCH mục, mỗi mục có tiêu đề riêng do admin viết.
#
# Bộ mục cứng của tờ giấy không phủ hết mọi nghề: nhiếp ảnh cần "Quyền sử dụng hình ảnh", dịch
# thuật cần "Quy tắc thuật ngữ". Áp cho CẢ HAI chế độ — đây là chữ admin ngồi soạn, nó không
# tranh chấp gì với phần AI đọc yêu cầu khách.  #Huynh
EXTRA_SECTIONS_KEY = "extra_sections"

# Chặn trên. Mẫu là thứ dùng chung cho mọi báo giá của mọi freelancer, nên một mẫu bị nhét 500
# mục là 500 mục đó in vào từng tờ giấy gửi khách.
MAX_EXTRA_SECTIONS = 12


def collect_extra_sections(
    template_content: dict, *, keep_untitled: bool = False
) -> list[dict]:
    """Nhặt các đầu mục tự soạn, cắt về đúng hai khoá `title`/`body`.

    Mặc định BỎ mục không có tiêu đề: một mục không tên in ra tờ giấy thành `<h2>9. </h2>` —
    số mục vẫn nhảy nhưng đầu đề trống trơn, khách đọc tưởng tài liệu lỗi.

    `keep_untitled=True` chỉ dùng cho MÀN SOẠN: admin vừa bấm "Thêm đầu mục" thì mục đó chưa có
    tên, mà lọc đi ngay thì nó không hiện lên giấy và admin không có chỗ nào để gõ tên vào.
    Đúng cùng nguyên tắc với cờ `editable` — bản gửi khách vẫn sạch.  #Huynh
    """
    raw = template_content.get(EXTRA_SECTIONS_KEY)
    if not isinstance(raw, list):
        return []

    out: list[dict] = []
    for item in raw[:MAX_EXTRA_SECTIONS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title and not keep_untitled:
            continue
        out.append({"title": title, "body": body})
    return out


def blocks_for(template_type: str) -> dict[str, str]:
    return (
        CONTRACT_TEMPLATE_BLOCKS if template_type == "contract" else PROPOSAL_TEMPLATE_BLOCKS
    )


def skeleton_blocks_for(template_type: str) -> dict[str, str]:
    return (
        CONTRACT_SKELETON_BLOCKS if template_type == "contract" else PROPOSAL_SKELETON_BLOCKS
    )


def skeleton_list_blocks_for(template_type: str) -> frozenset[str]:
    return (
        CONTRACT_SKELETON_LIST_BLOCKS
        if template_type == "contract"
        else PROPOSAL_SKELETON_LIST_BLOCKS
    )


def _collect(
    template_content: dict, blocks: dict[str, str], list_keys: frozenset[str]
) -> dict:
    """Nhặt các khối CÓ CHỮ ra khỏi `content` của mẫu, theo đúng bộ khoá được phép."""
    out: dict = {}
    for key in blocks:
        value = template_content.get(key)
        if key in list_keys:
            items = [str(x).strip() for x in value] if isinstance(value, list) else []
            items = [x for x in items if x]
            if items:
                out[key] = items
        elif isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def build_skeleton_content(template_content: dict, template_type: str) -> dict:
    """Dựng NỀN tài liệu từ mẫu, cho đường soạn KHÔNG dùng AI.

    Khác `apply_template_blocks` ở hai điểm: bộ khoá rộng hơn (với tới cả phần đặc thù dự án vì
    không có AI nào viết hộ), và dựng từ con số không chứ không phủ lên sẵn có.

    Mẫu chưa soạn khung thì trả `{}` — đó là kết quả HỢP LỆ, không phải lỗi: freelancer nhận một
    tờ giấy trống với đủ ô để tự điền. Chọn "khung trắng" (không mẫu) cũng đi vào đúng nhánh này.
    """
    if not isinstance(template_content, dict):
        return {}

    out = _collect(
        template_content,
        skeleton_blocks_for(template_type),
        skeleton_list_blocks_for(template_type),
    )

    if not str(out.get("standard_terms") or "").strip():
        legacy = template_content.get(LEGACY_BODY_KEY)
        if isinstance(legacy, str) and legacy.strip():
            out["standard_terms"] = legacy.strip()

    extra = collect_extra_sections(template_content)
    if extra:
        out[EXTRA_SECTIONS_KEY] = extra

    titles = collect_section_titles(template_content, template_type)
    if titles:
        out[SECTION_TITLES_KEY] = titles

    clauses = collect_clause_texts(template_content, template_type)
    if clauses:
        out[CLAUSE_TEXTS_KEY] = clauses

    an = collect_hidden_sections(template_content, template_type)
    if an:
        out[HIDDEN_SECTIONS_KEY] = an

    return out


def body_blocks_for(template_type: str) -> dict[str, str]:
    """Chỉ PHẦN THÂN: các mục thuộc bộ khung mà bộ điều khoản KHÔNG có.

    Đây là thứ phân biệt thật sự giữa hai chế độ. Ba khoá `out_of_scope`, `revision_policy`,
    `standard_terms` nằm trong CẢ HAI bộ, nên đếm gộp là một mẫu thuần điều khoản vẫn ra "có
    khung" — trong khi chọn nó ở tab khung thì mục 3 đến mục 6 của tờ giấy vẫn trắng. Người
    dùng đọc "Soạn sẵn: Ngoài phạm vi · Điều khoản chuẩn" rồi tưởng đỡ được kha khá, bấm vào
    mới biết phần phải gõ tay y hệt khung trắng.  #Huynh
    """
    terms = blocks_for(template_type)
    return {k: v for k, v in skeleton_blocks_for(template_type).items() if k not in terms}


def skeleton_block_labels(template_content: dict, template_type: str) -> list[str]:
    """Nhãn các mục PHẦN THÂN mẫu này đã soạn sẵn — để tab "Tự soạn từ khung" mô tả đúng.

    Tách khỏi `template_block_labels` vì hai tab mô tả hai thứ khác nhau: tab AI nói "mẫu này
    chèn thêm điều khoản gì", tab khung nói "mẫu này đỡ hộ tôi được bao nhiêu phần thân".

    CỐ Ý không kể phần điều khoản vào đây: rỗng phải có nghĩa là "mẫu này không đỡ được phần
    thân nào", để bộ chọn nói thẳng điều đó ra. Phần điều khoản mẫu vẫn mang theo được liệt kê
    riêng ở `blocks`, nên không mất thông tin nào.
    """
    if not isinstance(template_content, dict):
        return []

    blocks = body_blocks_for(template_type)
    return [
        blocks[key]
        for key in _collect(
            template_content, blocks, skeleton_list_blocks_for(template_type)
        )
    ]


def apply_template_blocks(content: dict, template_content: dict, template_type: str) -> dict:
    """Chép các khối của mẫu vào `content` của tài liệu. MẪU THẮNG AI.

    Hàm này chạy SAU khi AI sinh xong, nên chép đè nghĩa là mẫu thắng — đúng lý do admin ngồi
    soạn mẫu: để chữ đó không bị AI viết lại mỗi lần một kiểu.

    Khối để trống thì BỎ QUA, không ghi đè bằng chuỗi rỗng: mẫu điền vài khối, phần còn lại
    vẫn nhờ AI viết. Đó là cách một mẫu "dùng chung" sống chung được với nhiều loại dự án.
    """
    if not isinstance(template_content, dict):
        return content

    allowed = blocks_for(template_type)
    out = dict(content)

    for key in allowed:
        value = template_content.get(key)
        if key in LIST_BLOCKS:
            items = [str(x).strip() for x in value] if isinstance(value, list) else []
            items = [x for x in items if x]
            if items:
                out[key] = items
        elif isinstance(value, str) and value.strip():
            out[key] = value.strip()

    # Bí danh của bản cũ. Chỉ dùng khi mẫu KHÔNG khai `standard_terms` theo cấu trúc mới —
    # mẫu mới đã ghi rõ thì đừng để khoá cũ đè lên.
    if "standard_terms" not in out or not str(out.get("standard_terms") or "").strip():
        legacy = template_content.get(LEGACY_BODY_KEY)
        if isinstance(legacy, str) and legacy.strip():
            out["standard_terms"] = legacy.strip()

    # Đầu mục admin tự soạn áp cho CẢ HAI chế độ: đây là chữ admin ngồi viết, nó không tranh
    # chấp gì với phần AI vừa đọc yêu cầu khách.
    extra = collect_extra_sections(template_content)
    if extra:
        out[EXTRA_SECTIONS_KEY] = extra

    titles = collect_section_titles(template_content, template_type)
    if titles:
        out[SECTION_TITLES_KEY] = titles

    clauses = collect_clause_texts(template_content, template_type)
    if clauses:
        out[CLAUSE_TEXTS_KEY] = clauses

    an = collect_hidden_sections(template_content, template_type)
    if an:
        out[HIDDEN_SECTIONS_KEY] = an

    return out


def template_block_labels(template_content: dict, template_type: str) -> list[str]:
    """Nhãn các khối mẫu này THỰC SỰ có nội dung — cho bộ chọn xem trước."""
    if not isinstance(template_content, dict):
        return []

    labels: list[str] = []
    for key, label in blocks_for(template_type).items():
        value = template_content.get(key)
        filled = (
            any(str(x).strip() for x in value)
            if isinstance(value, list)
            else isinstance(value, str) and bool(value.strip())
        )
        if filled:
            labels.append(label)

    legacy = template_content.get(LEGACY_BODY_KEY)
    if not labels and isinstance(legacy, str) and legacy.strip():
        labels.append(blocks_for(template_type)["standard_terms"])
    return labels


def template_preview(template_content: dict, template_type: str, limit: int = 120) -> str:
    """Trích một đoạn ngắn của khối đầu tiên có nội dung.

    Bộ chọn chỉ cần đủ để phân biệt hai mẫu, không cần cả bài — nên KHÔNG trả nguyên `content`
    ra ngoài đường công khai.
    """
    if not isinstance(template_content, dict):
        return ""

    for key in blocks_for(template_type):
        value = template_content.get(key)
        text = (
            " · ".join(str(x).strip() for x in value if str(x).strip())
            if isinstance(value, list)
            else str(value or "")
        )
        text = " ".join(text.split())
        if text:
            return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    legacy = " ".join(str(template_content.get(LEGACY_BODY_KEY) or "").split())
    if not legacy:
        return ""
    return legacy if len(legacy) <= limit else legacy[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# TÊN các đầu mục có sẵn của tờ giấy.
#
# Trước đây mấy cái tên này viết cứng trong hai file Jinja, nên admin sửa được NỘI DUNG mà không
# sửa được TÊN mục — trong khi cách gọi tên lại là thứ khác nhau nhiều nhất giữa các nghề: chỗ
# gọi "Sản phẩm bàn giao", chỗ gọi "Hạng mục nghiệm thu".
#
# Đưa về đây để tên trở thành DỮ LIỆU: template chỉ tra bảng, mẫu của admin ghi đè được, và
# `collect_section_titles` bỏ những tên trùng mặc định nên `content` không phình ra vì mỗi lần
# admin bấm vào tiêu đề rồi bấm ra.  #Huynh
# ---------------------------------------------------------------------------
PROPOSAL_SECTION_DEFAULTS: dict[str, dict[str, str]] = {
    "party_a": {"vi": "Bên Cung Cấp Dịch Vụ", "en": "Service Provider (Party A)"},
    "party_b": {"vi": "Khách Hàng", "en": "Client (Party B)"},
    "project_overview": {"vi": "Tổng Quan Dự Án", "en": "Project Overview"},
    "scope_of_work": {"vi": "Phạm Vi Công Việc", "en": "Scope of Work"},
    "deliverables": {"vi": "Sản Phẩm Bàn Giao", "en": "Deliverables"},
    "timeline": {"vi": "Thời Gian Thực Hiện", "en": "Timeline"},
    "pricing": {"vi": "Chi Phí & Thanh Toán", "en": "Cost & Payment"},
    "additional_terms": {"vi": "Điều Khoản Bổ Sung", "en": "Additional Terms"},
    "assumptions": {"vi": "Ghi Chú & Giả Định", "en": "Notes & Assumptions"},
    "standard_terms": {"vi": "Điều Khoản Chuẩn Theo Lĩnh Vực", "en": "Standard Terms"},
    "confirmation": {"vi": "Xác Nhận", "en": "Confirmation"},
}

CONTRACT_SECTION_DEFAULTS: dict[str, dict[str, str]] = {
    "scope_of_work": {"vi": "Nội Dung và Phạm Vi Công Việc", "en": "Scope of Work"},
    "term": {"vi": "Thời Hạn Thực Hiện", "en": "Term of Performance"},
    "payment": {
        "vi": "Giá Trị Hợp Đồng và Phương Thức Thanh Toán",
        "en": "Contract Value and Payment",
    },
    "party_a_duties": {
        "vi": "Quyền và Nghĩa Vụ Của Bên A",
        "en": "Rights and Obligations of Party A",
    },
    "party_b_duties": {
        "vi": "Quyền và Nghĩa Vụ Của Bên B",
        "en": "Rights and Obligations of Party B",
    },
    "confidentiality": {"vi": "Bảo Mật Thông Tin", "en": "Confidentiality"},
    "ip_ownership": {"vi": "Quyền Sở Hữu Trí Tuệ", "en": "Intellectual Property"},
    "termination_clause": {"vi": "Sửa Đổi và Chấm Dứt Hợp Đồng", "en": "Amendment and Termination"},
    "dispute": {"vi": "Giải Quyết Tranh Chấp", "en": "Dispute Resolution"},
    "standard_terms": {"vi": "Điều Khoản Chuẩn Theo Lĩnh Vực", "en": "Standard Terms"},
    "custom_clauses": {"vi": "Điều Khoản Bổ Sung", "en": "Additional Terms"},
    "general": {"vi": "Điều Khoản Chung", "en": "General Provisions"},
}

SECTION_TITLES_KEY = "section_titles"

# Tên mục in ra một dòng tiêu đề, không phải một đoạn văn.
MAX_SECTION_TITLE_LEN = 120


def section_defaults_for(template_type: str) -> dict[str, dict[str, str]]:
    return (
        CONTRACT_SECTION_DEFAULTS
        if template_type == "contract"
        else PROPOSAL_SECTION_DEFAULTS
    )


def collect_section_titles(template_content: dict, template_type: str) -> dict[str, str]:
    """Tên mục admin đã ĐỔI, bỏ những tên trùng mặc định.

    Bỏ tên trùng mặc định là chuyện quan trọng chứ không phải tối ưu vặt: tiêu đề trên giấy là
    một ô sửa tại chỗ, nên admin chỉ cần bấm vào rồi bấm ra là ô đó "lưu" lại đúng cái tên cũ.
    Không lọc thì `content` đầy khoá vô nghĩa, và tệ hơn: tờ giấy mất dòng tiếng Anh phụ (dòng
    đó chỉ hiện khi tên CHƯA bị đổi).
    """
    raw = template_content.get(SECTION_TITLES_KEY)
    if not isinstance(raw, dict):
        return {}

    defaults = section_defaults_for(template_type)
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in defaults or not isinstance(value, str):
            continue
        title = " ".join(value.split())[:MAX_SECTION_TITLE_LEN].strip()
        if not title or title == defaults[key]["vi"]:
            continue
        out[key] = title
    return out


# ---------------------------------------------------------------------------
# CHỮ trong các điều có sẵn của tờ giấy.
#
# Cùng lý do với `*_SECTION_DEFAULTS`, nhưng cho phần THÂN: trước đây admin đổi được TÊN điều mà
# không đổi được một chữ nào bên trong — bấm vào tiêu đề thì sửa được, bấm vào đoạn ngay dưới
# thì không. Không nhất quán, và khoá cứng đúng những điều pháp lý mà mỗi nghề diễn đạt một kiểu.
#
# DẪN CHIẾU THEO TÊN, KHÔNG THEO SỐ. Bản trước viết "đã cam kết tại Điều 1 và Điều 2", "thanh
# toán theo Điều 3" — số cứng. Từ khi admin thêm/bớt/đổi tên được đầu mục thì mấy con số đó sai
# bất cứ lúc nào, mà lại sai trên giấy tờ pháp lý gửi khách.  #Huynh
# ---------------------------------------------------------------------------
PROPOSAL_CLAUSE_DEFAULTS: dict[str, object] = {
    "confirmation": "Vui lòng xác nhận đồng ý để bắt đầu triển khai dự án.",
}

CONTRACT_CLAUSE_DEFAULTS: dict[str, object] = {
    "preamble_law": (
        "Căn cứ Bộ luật Dân sự số 91/2015/QH13 và các quy định pháp luật hiện hành có liên quan;"
    ),
    "preamble_need": "Căn cứ nhu cầu và khả năng thực tế của hai Bên;",
    "intro": (
        "Sau khi bàn bạc, hai Bên thống nhất ký kết Hợp đồng Dịch vụ này "
        '(gọi tắt là "Hợp Đồng") với các điều khoản như sau:'
    ),
    "term": (
        "Tiến độ và các mốc bàn giao thực hiện theo điều khoản thanh toán và nội dung công "
        "việc hai Bên đã thống nhất."
    ),
    "late_payment": (
        "Trường hợp Bên B thanh toán trễ hạn, Bên B chịu lãi suất chậm trả theo thỏa thuận "
        "của hai Bên trên số tiền chậm thanh toán."
    ),
    "party_a_duties": [
        "Thực hiện công việc đúng nội dung, chất lượng và tiến độ đã cam kết trong Hợp đồng.",
        (
            "Chủ động thông báo cho Bên B khi có phát sinh ảnh hưởng đến tiến độ "
            "hoặc phạm vi công việc."
        ),
        # KHÔNG dẫn chiếu tới Điều Bảo mật: điều đó thuộc tầng 3 (admin tắt được), nên nhắc
        # đích danh nó là có ngày câu này trỏ vào một điều không còn trên giấy.
        "Bảo mật thông tin, tài liệu của Bên B trong quá trình thực hiện Hợp đồng.",
        "Có quyền yêu cầu Bên B thanh toán đầy đủ, đúng hạn theo điều khoản thanh toán.",
    ],
    "party_b_duties": [
        (
            "Cung cấp đầy đủ, kịp thời thông tin, tài liệu, quyền truy cập cần thiết "
            "để Bên A thực hiện công việc."
        ),
        "Thanh toán đầy đủ, đúng hạn theo điều khoản thanh toán.",
        (
            "Có quyền yêu cầu Bên A báo cáo tiến độ và nghiệm thu sản phẩm theo các mốc "
            "đã thỏa thuận."
        ),
    ],
    "ip_ownership": (
        "Toàn bộ quyền sở hữu trí tuệ đối với sản phẩm bàn giao thuộc về Bên B kể từ thời "
        "điểm Bên B thanh toán đầy đủ giá trị Hợp đồng, trừ khi hai Bên có thỏa thuận khác "
        "bằng văn bản."
    ),
    "confidentiality": (
        "Hai Bên cam kết bảo mật mọi thông tin, tài liệu không công khai trao đổi trong quá "
        "trình thực hiện Hợp đồng, không tiết lộ cho bên thứ ba nếu không có sự đồng ý bằng "
        "văn bản của Bên còn lại, trừ trường hợp pháp luật yêu cầu. Nghĩa vụ này vẫn có hiệu "
        "lực sau khi Hợp đồng kết thúc."
    ),
    "dispute": (
        "Mọi tranh chấp trước hết được hai Bên giải quyết qua thương lượng, hòa giải; nếu "
        "không đạt thỏa thuận, tranh chấp được đưa ra Tòa án nhân dân có thẩm quyền giải "
        "quyết theo quy định pháp luật."
    ),
    "general": (
        "Hợp đồng có hiệu lực kể từ ngày ký, được lập thành 02 (hai) bản có giá trị pháp lý "
        "như nhau, mỗi Bên giữ 01 (một) bản."
    ),
}

CLAUSE_TEXTS_KEY = "clause_texts"

# Khoá nhận DANH SÁCH gạch đầu dòng thay vì một đoạn văn.
CLAUSE_LIST_KEYS: frozenset[str] = frozenset({"party_a_duties", "party_b_duties"})


def clause_defaults_for(template_type: str) -> dict[str, object]:
    return (
        CONTRACT_CLAUSE_DEFAULTS
        if template_type == "contract"
        else PROPOSAL_CLAUSE_DEFAULTS
    )


def collect_clause_texts(template_content: dict, template_type: str) -> dict[str, object]:
    """Chữ admin đã ĐỔI trong các điều có sẵn, bỏ những chỗ trùng bản mặc định.

    Bỏ chỗ trùng mặc định vì cùng lý do với tên mục: đoạn văn nào cũng là ô sửa tại chỗ, nên chỉ
    cần bấm vào rồi bấm ra là nó "lưu" lại đúng chữ cũ, và `content` phình lên vì những khoá
    không đổi gì.
    """
    raw = template_content.get(CLAUSE_TEXTS_KEY)
    if not isinstance(raw, dict):
        return {}

    defaults = clause_defaults_for(template_type)
    out: dict[str, object] = {}
    for key, value in raw.items():
        if key not in defaults:
            continue
        if key in CLAUSE_LIST_KEYS:
            if not isinstance(value, list):
                continue
            items = [" ".join(str(x).split()) for x in value]
            items = [x for x in items if x]
            if items and items != defaults[key]:
                out[key] = items
            continue
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text != defaults[key]:
            out[key] = text
    return out


# ---------------------------------------------------------------------------
# BA TẦNG QUYỀN SỬA MẪU
#
# Trước bản này "mục nào bỏ được" là hệ quả TÌNH CỜ của cách render: mục nào có chữ mặc định thì
# không bao giờ rỗng nên không bao giờ biến mất. Kết quả: báo giá bỏ được 7/11, hợp đồng chỉ
# 2/12 — không theo một chính sách nào, mà theo việc admin đã gõ gì.
#
# Nay chia ba tầng theo HẬU QUẢ KHI THIẾU:
#
#   Tầng 1 — khoá cứng      : thiếu thì tài liệu không còn là tài liệu đó (hai bên, giá, đối tượng)
#   Tầng 2 — sửa chữ, không tắt : thứ PHIẾU ĐỀ TÀI đã hứa, hoặc bộ khung tối thiểu
#   Tầng 3 — tắt được       : tuỳ nghề, không ảnh hưởng giá trị của tài liệu
#
# CĂN CỨ chọn tầng 2 KHÔNG phải Bộ luật Dân sự: Phiếu đề tài tự ghi hợp đồng "KHÔNG phải văn bản
# pháp lý chính thức". Căn cứ là chính Phiếu — nó định nghĩa "báo giá dịch vụ đầy đủ" gồm *phạm
# vi công việc, sản phẩm bàn giao, tiến độ, giá, điều khoản thanh toán*. Năm thứ đó không tắt
# được vì tắt đi là sản phẩm không còn làm đúng thứ đã hứa.
#
# Lý do thứ hai, mạnh không kém: RỦI RO TẬP TRUNG. Mẫu dùng chung cho mọi freelancer — admin bỏ
# điều SHTT một lần thì mọi hợp đồng sinh từ mẫu đó đều thiếu, mà freelancer không có cách nào
# biết.  #Huynh
# ---------------------------------------------------------------------------

# Tầng 3 của báo giá. `pricing`/`party_a`/`party_b`/`confirmation` (tầng 1) và bốn mục Phiếu
# liệt kê (tầng 2) CỐ Ý vắng mặt.
PROPOSAL_HIDEABLE: frozenset[str] = frozenset(
    {"project_overview", "additional_terms", "assumptions", "standard_terms"}
)

# Tầng 3 của hợp đồng. Nới hơn báo giá vì Phiếu nhấn "cấu hình được theo loại nghề" và đã tự
# miễn trừ giá trị pháp lý — buổi chụp một ngày không cần điều bảo mật riêng.
CONTRACT_HIDEABLE: frozenset[str] = frozenset(
    {"confidentiality", "termination_clause", "standard_terms", "custom_clauses"}
)

HIDDEN_SECTIONS_KEY = "hidden_sections"


def hideable_for(template_type: str) -> frozenset[str]:
    return CONTRACT_HIDEABLE if template_type == "contract" else PROPOSAL_HIDEABLE


def collect_hidden_sections(template_content: dict, template_type: str) -> list[str]:
    """Những mục admin CHỦ Ý tắt khỏi mọi tài liệu sinh từ mẫu này.

    Phải là một khoá RIÊNG chứ không nhồi vào `section_titles`/`clause_texts`: hai hàm kia xây
    trên tiên đề "có giá trị = có nội dung, rỗng = chưa đụng vào", và cả hai đều lọc bỏ giá trị
    rỗng lẫn giá trị trùng mặc định. Mã hoá "ẩn" bằng tên rỗng là bị vứt im lặng.

    Phân biệt sống còn — TẮT ≠ TRỐNG:
    * tắt  = admin quyết mục đó không thuộc mẫu này, áp cho MỌI tài liệu;
    * trống = mẫu chưa soạn, để AI hoặc freelancer điền theo từng dự án.

    Allowlist theo tầng 3, nên nhét `pricing` hay `scope_of_work` vào đây cũng không đi tới đâu —
    đó là cửa sau để tổng tiền biến khỏi tờ giấy gửi khách.
    """
    raw = template_content.get(HIDDEN_SECTIONS_KEY)
    if not isinstance(raw, list):
        return []

    duoc_phep = hideable_for(template_type)
    out: list[str] = []
    for item in raw:
        key = str(item).strip()
        if key in duoc_phep and key not in out:
            out.append(key)
    return out
