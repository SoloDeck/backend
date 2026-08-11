from pydantic import BaseModel


class ProposalGenerationInput(BaseModel):
    """Đầu vào để AI soạn báo giá.

    Chia làm HAI nhóm và KHÔNG được lẫn lộn:

    * **Yêu cầu dự án đã ghi nhận** — ``client_inquiry``, ``client_budget``,
      ``client_timeline``, ``project_description``, ``estimated_scope``. Khách gõ qua biểu
      mẫu hay freelancer chép lại từ điện thoại/Zalo đều là YÊU CẦU, dùng để soạn báo giá.
    * **Freelancer tự chọn trong phần mềm** — ``pricing_tier``, ``urgency``,
      ``freelancer_estimated_value`` (ô "Giá trị dự kiến" lúc tạo deal).

    Vì sao phải tách: "Giá trị dự kiến" là con số FREELANCER tự ước, KHÔNG phải khách
    báo. Trước đây nó được đưa vào AI dưới nhãn ``Budget`` chung chung nên model tưởng
    khách đã chốt ngân sách. Nhãn dữ liệu mập mờ thì AI giỏi mấy cũng suy sai.  #Huynh

    ⚠️ ``project_description`` TỪNG bị xếp nhầm sang nhóm hai dưới nhãn "Ghi chú nội bộ".
    Nó chính là ``deals.notes`` — ô "Nội dung yêu cầu" trên giao diện — nên khách ghi
    "Thời gian build: 5 tháng" thì báo giá vẫn ghi "hai bên thống nhất sau".  #Huynh
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
