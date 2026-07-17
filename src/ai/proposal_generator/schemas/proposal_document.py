from pydantic import BaseModel


class PricingLineItem(BaseModel):
    """Một dòng trong bảng giá — mô tả + thành tiền đã định dạng sẵn (VND)."""

    description: str
    amount: str


class ProposalDocument(BaseModel):
    # --- Bên A: người gửi báo giá ---
    #
    # Thiếu email/SĐT là tờ báo giá CỤT: khách đọc xong muốn trả lời cũng không biết bằng
    # cách nào. Bản trước chỉ ghi "Được chuẩn bị bởi <tên>".  #Huynh
    freelancer_name: str
    freelancer_email: str = ""
    freelancer_phone: str = ""

    # --- Bên B: khách hàng ---
    client_name: str
    client_email: str = ""
    client_phone: str = ""
    company_name: str | None = None

    project_type: str

    proposal_date: str

    # Hạn hiệu lực. Báo giá không có hạn là giá bị treo vô thời hạn — sáu tháng sau khách
    # quay lại đòi đúng con số cũ trong khi giá thị trường đã khác.  #Huynh
    valid_until: str = ""

    project_overview: str

    scope_of_work: list[str]

    deliverables: list[str]

    timeline: str

    # Bảng giá có cấu trúc. Khi có `pricing_line_items`, template render một BẢNG (hạng mục
    # | thành tiền) + dòng tổng — giống hệt card trên màn hình. Khi rỗng, rơi về chuỗi
    # `pricing` (báo giá cũ chưa có bảng, hoặc AI trả về chuỗi).
    #
    # Đây là mấu chốt để card và PDF KHÔNG lệch nhau: cả hai render từ cùng một cấu trúc.
    #  #Huynh
    pricing_line_items: list[PricingLineItem] = []

    pricing_total: str = ""

    pricing: str

    payment_terms: str

    assumptions: str

    # --- Điều khoản bổ sung: thứ CHỐNG SCOPE CREEP ---
    #
    # "Phạm vi KHÔNG bao gồm" là dòng phòng thủ quan trọng nhất của freelancer: tranh cãi
    # "cái này em tưởng có trong giá rồi" xảy ra TRƯỚC khi ký hợp đồng, nên phải nằm ở BÁO
    # GIÁ mới đúng lúc. Ta đã có mấy trường này trong module hợp đồng — nhưng lúc đó thì
    # muộn rồi.  #Huynh
    out_of_scope: list[str] = []
    revision_policy: str = ""
