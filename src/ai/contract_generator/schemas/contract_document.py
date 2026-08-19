"""Document phẳng để render hợp đồng ra HTML/PDF.

Song song với ``proposal_document.ProposalDocument``: một struct phẳng, đã định dạng
sẵn (tiền tệ, ngày tháng đều là chuỗi), để template Jinja chỉ việc in ra — không tính
toán gì trong template.

Vì sao tách riêng khỏi ``ContractContentDTO`` (nội dung AI viết): DTO chỉ có mấy điều
khoản văn xuôi + parties. Còn tờ hợp đồng thật cần thêm ngày ký, số hợp đồng, lịch
thanh toán, khối chữ ký... Những thứ đó neo vào DB (contract, milestones, dates), không
phải do AI sinh. ``build_contract_document`` ghép hai nguồn lại.  #Huynh
"""

from pydantic import BaseModel


class ContractMilestoneLine(BaseModel):
    """Một dòng trong lịch thanh toán — mô tả + số tiền đã định dạng (VND) + hạn."""

    description: str
    amount: str
    due_date: str = ""


class ExtraSection(BaseModel):
    """Một đầu mục do ADMIN tự soạn — tên mục nằm trong dữ liệu, không nằm trong template.

    Bộ mục cứng của tờ giấy không thể phủ hết mọi nghề: nhiếp ảnh cần "Quyền sử dụng hình ảnh",
    dịch thuật cần "Quy tắc thuật ngữ". Đánh số tự động theo bộ đếm chung nên chèn bao nhiêu
    mục thì số vẫn liền mạch.  #Huynh
    """

    title: str = ""
    body: str = ""


class ContractDocument(BaseModel):
    # --- Đầu trang ---
    project_name: str = ""
    contract_number: str = ""
    contract_date: str = ""
    # "Báo giá đã được Bên B chấp nhận (đính kèm Phụ lục A)" — hợp đồng dịch vụ VN luôn
    # dẫn chiếu tới báo giá làm căn cứ. Xem HopDongMau.pdf.  #Huynh
    proposal_reference: str = ""

    # --- BÊN A: bên cung cấp dịch vụ (freelancer) ---
    #
    # Thiếu email/SĐT thì hợp đồng CỤT y như báo giá cụt: có tranh chấp cũng không biết
    # liên hệ ai. business_name có thì bên A ghi là hộ kinh doanh/công ty.  #Huynh
    freelancer_name: str = ""
    freelancer_business_name: str = ""
    freelancer_email: str = ""
    freelancer_phone: str = ""
    freelancer_address: str = ""

    # --- BÊN B: bên sử dụng dịch vụ (khách hàng) ---
    client_name: str = ""
    client_company: str = ""
    client_email: str = ""
    client_phone: str = ""
    client_address: str = ""

    # --- Điều khoản (AI viết, văn xuôi) ---
    scope_of_work: str = ""
    payment_terms: str = ""
    revision_policy: str = ""
    ip_ownership: str = ""
    termination_clause: str = ""
    governing_law: str = ""
    custom_clauses: str = ""
    # Điều khoản chuẩn lấy NGUYÊN VĂN từ thư viện mẫu của admin (theo nghề). AI không sinh
    # trường này — service gán sau khi sinh xong. Rỗng = không có mẫu khớp.
    standard_terms: str = ""

    # --- Lịch thanh toán (từ contract_payment_milestones) ---
    milestones: list[ContractMilestoneLine] = []
    total_amount: str = ""

    # --- Hiệu lực ---
    effective_date: str = ""
    end_date: str = ""
    version_number: int = 1

    # Đầu mục admin tự thêm, render ngay trước phần cuối tờ giấy.
    extra_sections: list[ExtraSection] = []

    # Tên đầu mục admin đã đổi. Khoá vắng mặt = dùng tên mặc định
    # (xem `*_SECTION_DEFAULTS`).
    section_titles: dict[str, str] = {}

    # Chữ admin đã sửa trong các điều CÓ SẴN. Khoá vắng mặt = dùng bản mặc định
    # (xem `*_CLAUSE_DEFAULTS`).
    clause_texts: dict = {}

    # Mục admin CHỦ Ý tắt khỏi mẫu này. Khác hẳn "mục trống": trống là chưa ai
    # điền, tắt là quyết định mục đó không thuộc về tài liệu.
    hidden_sections: list[str] = []
