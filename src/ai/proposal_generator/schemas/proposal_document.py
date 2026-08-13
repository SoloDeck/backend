from pydantic import BaseModel


class PricingLineItem(BaseModel):
    """Một dòng trong bảng giá — mô tả + thành tiền đã định dạng sẵn (VND) + thời điểm thu.

    `due` gộp vào đây từ khi bỏ mục "8. Điều Khoản Thanh Toán": mỗi hạng mục vừa là công việc
    vừa là một đợt thu tiền, nên tách làm hai bảng chỉ tạo ra hai bản sao của cùng một danh
    sách — khách đọc xong không biết bảng nào là thật.  #Huynh
    """

    description: str
    amount: str
    due: str = ""


class PaymentMilestone(BaseModel):
    """Một ĐỢT thanh toán — mô tả + % (của tổng) HOẶC số tiền + thời điểm/điều kiện.

    Linh hoạt N đợt (mặc định 2: đặt cọc khi ký + phần còn lại khi bàn giao). Đây là nguồn
    cấu trúc để render "Điều khoản thanh toán" trên báo giá và (Stage 2) sinh task thanh toán.
    """

    label: str
    percent: int | None = None
    amount: str = ""
    due: str = ""


def default_payment_milestones() -> list[PaymentMilestone]:
    """Lịch thanh toán CHUẨN khi báo giá không nêu mốc nào: đặt cọc 50% + bàn giao 50%.

    Trùng với mặc định nêu trong prompt. Dùng làm điểm neo để LUÔN có mốc thu tiền — kể cả
    khi model không trả về `payment_milestones` có cấu trúc (chỉ ghi văn xuôi ở
    `payment_terms`) — nhờ đó Stage 2 vẫn sinh được task "Thu tiền:".  #Huynh
    """
    return [
        PaymentMilestone(
            label="Đặt cọc khi ký hợp đồng",
            percent=50,
            due="Khi ký hợp đồng / trước khi bắt đầu",
        ),
        PaymentMilestone(
            label="Thanh toán khi nghiệm thu & bàn giao",
            percent=50,
            due="Khi nghiệm thu & bàn giao",
        ),
    ]


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

    # Các ĐỢT thanh toán có cấu trúc (linh hoạt N đợt). Template render thành bảng
    # "Điều khoản thanh toán"; khi rỗng thì rơi về chuỗi `payment_terms`.
    payment_milestones: list[PaymentMilestone] = []

    assumptions: str

    # --- Điều khoản bổ sung: thứ CHỐNG SCOPE CREEP ---
    #
    # "Phạm vi KHÔNG bao gồm" là dòng phòng thủ quan trọng nhất của freelancer: tranh cãi
    # "cái này em tưởng có trong giá rồi" xảy ra TRƯỚC khi ký hợp đồng, nên phải nằm ở BÁO
    # GIÁ mới đúng lúc. Ta đã có mấy trường này trong module hợp đồng — nhưng lúc đó thì
    # muộn rồi.  #Huynh
    out_of_scope: list[str] = []
    revision_policy: str = ""

    # Điều khoản chuẩn lấy NGUYÊN VĂN từ thư viện mẫu của admin (theo nghề). AI không sinh
    # trường này — service gán sau khi sinh. Rỗng = không có mẫu khớp.
    standard_terms: str = ""
