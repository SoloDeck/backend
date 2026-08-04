import json
from typing import Any

from src.ai.shared.llm_provider import BaseLLMProvider
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt

from ..schemas.proposal_content import ProposalContent
from ..schemas.proposal_generation_input import ProposalGenerationInput

# Hai tiêu đề là GIAO KÈO với `proposal_generator/prompts/system.txt` — prompt gọi tên chúng
# nguyên văn để ra luật timeline. Sửa một phía mà quên phía kia thì luật trỏ vào khối không
# tồn tại, và AI im lặng viết bậy vào bản báo giá GỬI THẲNG CHO KHÁCH.  #Huynh
PROPOSAL_REQUIREMENT_HEADING = "## YÊU CẦU DỰ ÁN — CĂN CỨ ĐỂ SOẠN BÁO GIÁ"
PROPOSAL_OWN_HEADING = "## FREELANCER TỰ CHỌN TRONG PHẦN MỀM — KHÔNG PHẢI LỜI KHÁCH"


class ProposalGenerationService:
    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider
        self.last_usage: dict[str, Any] | None = None

    def _build_context(self, request: ProposalGenerationInput) -> str:
        """Dựng ngữ cảnh gửi cho AI — ranh giới nằm ở "đây có phải yêu cầu đã ghi nhận không".

        `project_description` chính là `deals.notes`, tức ô "Nội dung yêu cầu" trên giao diện
        (xem `proposal_generator/chain.py`: `project_description = deal_data["notes"]`). Bản
        trước dán nhãn nó là "Ghi chú nội bộ" rồi xếp vào khối "không phải lời khách", trong
        khi prompt ra luật `timeline` CHỈ được viết dựa trên khối lời khách.

        Hậu quả: khách ghi "Thời gian build: 5 tháng", freelancer dán nguyên văn vào ô "Nội
        dung yêu cầu", nhưng báo giá gửi đi vẫn ghi "hai bên thống nhất sau". Đúng con số cần
        dùng thì bị coi như không tồn tại. Cùng gốc bệnh với lead_qualifier.

        Ranh giới ĐÚNG: ba thứ dưới đây là LỰA CHỌN của freelancer trong phần mềm, không phải
        yêu cầu khách nêu — mức giá áp dụng, độ gấp, và con số sẽ chào. Riêng chúng nằm khối
        2. Còn mô tả yêu cầu thì khách gõ hay freelancer chép lại cũng vẫn là yêu cầu.

        Luật "khách chưa nêu thời hạn thì KHÔNG được bịa" vẫn giữ nguyên — báo giá này gửi
        thẳng cho khách, bịa một mốc là hứa hộ họ điều họ chưa đồng ý.  #Huynh
        """
        requirement: list[str] = [f"- Loại dự án: {request.project_type}"]

        if request.client_inquiry:
            requirement.append(f"- Nguyên văn yêu cầu khách gửi: {request.client_inquiry}")

        if request.project_description:
            requirement.append(f"- Nội dung yêu cầu: {request.project_description}")

        if request.estimated_scope:
            requirement.append(f"- Phạm vi ước tính: {request.estimated_scope}")

        if request.service_category:
            requirement.append(f"- Nhóm dịch vụ: {request.service_category}")

        if request.client_budget:
            requirement.append(f"- Ngân sách khách nêu: {request.client_budget}")

        if request.client_timeline:
            requirement.append(f"- Thời gian khách muốn: {request.client_timeline}")

        own: list[str] = []

        if request.pricing_tier:
            own.append(f"- Mức giá áp dụng: {request.pricing_tier}")

        if request.urgency:
            own.append(f"- Độ gấp: {request.urgency}")

        if request.freelancer_estimated_value:
            own.append(
                "- Giá freelancer sẽ chào "
                f"(DÙNG ĐÚNG CON SỐ NÀY, không tự tính lại): "
                f"{request.freelancer_estimated_value}"
            )

        blocks: list[str] = [PROPOSAL_REQUIREMENT_HEADING, *requirement]
        if own:
            blocks += ["", PROPOSAL_OWN_HEADING, *own]
        blocks += [
            "",
            "## CÁC BÊN",
            f"- Khách hàng: {request.client_name}",
            f"- Công ty khách: {request.company_name or '(không có)'}",
            f"- Freelancer: {request.freelancer_name}",
        ]
        return "\n".join(blocks)

    async def generate(
        self,
        request: ProposalGenerationInput,
    ) -> ProposalContent:

        prompt_template = load_prompt("proposal_generator")

        prompt = f"{prompt_template}\n\n{self._build_context(request)}\n"

        response = await self.provider.generate(
            prompt=prompt,
            temperature=0.2,
            json_mode=True,
        )

        self.last_usage = response.usage

        try:
            content = extract_json_object(response.text)

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model did not return valid JSON:\n{response.text}"
            ) from exc

        return ProposalContent(**content)