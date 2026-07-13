from pydantic import BaseModel


class ProposalGenerationInput(BaseModel):
    """Đầu vào để AI soạn báo giá.

    Chia làm HAI nhóm và KHÔNG được lẫn lộn:

    * **Khách hàng nói gì** — ``client_inquiry``, ``client_budget``, ``client_timeline``.
      Là lời khách, lấy từ Biểu mẫu tiếp nhận (bảng ``deal_intakes``).
    * **Freelancer tự nhập** — ``project_description`` (ghi chú nội bộ),
      ``freelancer_estimated_value`` (ô "Giá trị dự kiến" lúc tạo deal).

    Vì sao phải tách: "Giá trị dự kiến" là con số FREELANCER tự ước, KHÔNG phải khách
    báo. Trước đây nó được đưa vào AI dưới nhãn ``Budget`` chung chung nên model tưởng
    khách đã chốt ngân sách. Nhãn dữ liệu mập mờ thì AI giỏi mấy cũng suy sai.  #Huynh
    """

    client_name: str
    company_name: str | None = None

    project_type: str

    # --- Khách hàng nói gì (nguồn tin đáng tin nhất) ---------------------------------
    #
    # AI soạn báo giá TRƯỚC ĐÂY KHÔNG HỀ được đọc mấy trường này, dù chúng nằm sẵn trong
    # DB và lead_qualifier vẫn đọc bình thường. Kết quả: khách viết hẳn một đoạn mô tả
    # yêu cầu mà báo giá vẫn mỏng dính, vì AI chỉ được đưa cho mỗi ghi chú nội bộ.
    client_inquiry: str | None = None
    client_budget: str | None = None
    client_timeline: str | None = None

    # --- Freelancer tự nhập ---------------------------------------------------------
    project_description: str = ""
    estimated_scope: str | None = None
    freelancer_estimated_value: str | None = None
    urgency: str | None = None

    service_category: str = ""
    pricing_tier: str = ""

    freelancer_name: str = ""
