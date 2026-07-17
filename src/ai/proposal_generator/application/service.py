import json
from typing import Any

from groq import Groq

from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt
from src.ai.shared.token_usage import extract_usage

from ..schemas.proposal_content import ProposalContent
from ..schemas.proposal_generation_input import ProposalGenerationInput

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class ProposalGenerationService:
    def __init__(self, client: Groq):
        self.client = client
        # Token của lần gọi gần nhất — service đọc để ghi vào ai_cost_records.
        self.last_usage: dict[str, Any] | None = None

    # _clean_response() cũ chỉ cắt fence khi CẢ chuỗi bắt đầu bằng ``` — cùng bug với
    # lead_qualifier. Đã thay bằng extract_json_object() dùng chung.  #Huynh

    def _build_context(self, request: ProposalGenerationInput) -> str:
        """Dựng ngữ cảnh gửi cho AI, TÁCH BẠCH lời khách và thông tin freelancer tự nhập.

        Trước đây tất cả gộp thành một danh sách phẳng ``Client Name / Project Type /
        Budget / ...``. Hai hậu quả:

        1. Dòng ``Budget`` thực chất là ô "Giá trị dự kiến" do FREELANCER tự nhập, nhưng
           model đọc thấy thì tưởng khách đã chốt ngân sách.
        2. Nguyên văn yêu cầu của khách (``deal_intakes.inquiry_text``) **không hề được
           đưa vào** — nguồn tin giàu nhất bị bỏ qua, nên báo giá viết ra rất mỏng.

        Giờ chia hai khối, và prompt ra luật: thời hạn/thanh toán CHỈ được lấy từ khối
        "KHÁCH HÀNG NÓI GÌ".  #Huynh
        """
        said: list[str] = []
        if request.client_inquiry:
            said.append(f"- Nguyên văn yêu cầu: {request.client_inquiry}")
        if request.client_budget:
            said.append(f"- Ngân sách khách nêu: {request.client_budget}")
        if request.client_timeline:
            said.append(f"- Thời gian khách muốn: {request.client_timeline}")

        own: list[str] = [f"- Loại dự án: {request.project_type}"]
        if request.project_description:
            own.append(f"- Ghi chú nội bộ: {request.project_description}")
        if request.estimated_scope:
            own.append(f"- Phạm vi ước tính: {request.estimated_scope}")
        if request.service_category:
            own.append(f"- Nhóm dịch vụ: {request.service_category}")
        if request.pricing_tier:
            own.append(f"- Mức giá áp dụng: {request.pricing_tier}")
        if request.urgency:
            own.append(f"- Độ gấp: {request.urgency}")
        if request.freelancer_estimated_value:
            own.append(
                f"- Giá freelancer sẽ chào (DÙNG ĐÚNG CON SỐ NÀY, không tự tính lại): "
                f"{request.freelancer_estimated_value}"
            )

        return "\n".join(
            [
                "## KHÁCH HÀNG NÓI GÌ",
                *(said or ["- (Khách chưa cung cấp thông tin nào)"]),
                "",
                "## THÔNG TIN FREELANCER TỰ NHẬP (không phải lời khách)",
                *own,
                "",
                "## CÁC BÊN",
                f"- Khách hàng: {request.client_name}",
                f"- Công ty khách: {request.company_name or '(không có)'}",
                f"- Freelancer: {request.freelancer_name}",
            ]
        )

    def generate(self, request: ProposalGenerationInput) -> ProposalContent:

        prompt_template = load_prompt("proposal_generator")

        prompt = f"{prompt_template}\n\n{self._build_context(request)}\n"

        response = self.client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.2,
            # Buộc model trả JSON thuần. Thiếu cờ này, llama-4-scout bọc câu trả lời
            # trong văn bản và parser vỡ — đúng bug đã làm chết lead_qualifier.  #Huynh
            response_format={"type": "json_object"},
        )

        self.last_usage = extract_usage(response, model=getattr(response, "model", None) or MODEL)

        raw_response = response.choices[0].message.content or ""

        try:
            content = extract_json_object(raw_response)

        except json.JSONDecodeError as exc:
            raise ValueError(f"Model did not return valid JSON:\n{raw_response}") from exc

        return ProposalContent(**content)
