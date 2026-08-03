import json
from typing import Any

from src.ai.shared.llm_provider import BaseLLMProvider
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt

from ..schemas.proposal_content import ProposalContent
from ..schemas.proposal_generation_input import ProposalGenerationInput


class ProposalGenerationService:
    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider
        self.last_usage: dict[str, Any] | None = None

    def _build_context(self, request: ProposalGenerationInput) -> str:
        """Dựng ngữ cảnh gửi cho AI."""

        said: list[str] = []

        if request.client_inquiry:
            said.append(f"- Nguyên văn yêu cầu: {request.client_inquiry}")

        if request.client_budget:
            said.append(f"- Ngân sách khách nêu: {request.client_budget}")

        if request.client_timeline:
            said.append(f"- Thời gian khách muốn: {request.client_timeline}")

        own: list[str] = [
            f"- Loại dự án: {request.project_type}",
        ]

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
                "- Giá freelancer sẽ chào "
                f"(DÙNG ĐÚNG CON SỐ NÀY, không tự tính lại): "
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