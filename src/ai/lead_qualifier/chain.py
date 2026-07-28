"""LeadQualifier AI chain."""

import json
from typing import Any

import structlog

from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt, prompt_version
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()


def build_qualifier_prompt(
    prompt_template: str,
    inquiry_text: str,
    profession: str | None = None,
    scam_hint: str | None = None,
) -> str:
    """Ghép prompt cuối gửi LLM: template tĩnh + ngữ cảnh nghề (nếu có) + inquiry.

    Tách riêng để test được mà không cần gọi LLM. ``profession``/``scam_hint`` là
    DỮ LIỆU đầu vào theo request, không nằm trong system.txt nên KHÔNG đổi
    prompt_version.
    """
    context_lines = ""
    if profession:
        context_lines += f"Nghề của freelancer: {profession}\n"
    if scam_hint:
        context_lines += f"Mẫu lừa đảo phổ biến của nghề này: {scam_hint}\n"

    return f"""{prompt_template}

{context_lines}Client Inquiry:
{inquiry_text}
"""


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"

    def _build_chain(self) -> Any:
        """Required by BaseAIChain."""
        return None

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """Bóc khối JSON ra khỏi câu trả lời của model.

        Phần bóc nằm ở ``src/ai/shared/json_output.py`` để proposal_generator dùng
        chung — trước đây mỗi chain một bản, sửa nơi này quên nơi kia.
        """
        try:
            return extract_json_object(raw)
        except json.JSONDecodeError as exc:
            log.error(
                "ai.lead_qualifier.parse_failed",
                raw=raw,
                error=str(exc),
            )
            raise AIOutputParseError(
                f"Failed to parse lead qualification output: {exc}",
                raw_output=raw,
            ) from exc

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        inquiry_text = kwargs.get("inquiry_text")
        if not inquiry_text:
            raise ValueError("inquiry_text is required for LeadQualifier")

        # Ngữ cảnh nghề của freelancer (nếu có): nhãn nghề để ước giá đúng nghề,
        # và mẫu lừa đảo đặc thù nghề để đối chiếu.
        profession = kwargs.get("profession")
        scam_hint = kwargs.get("scam_hint")

        # KHÔNG có prompt dự phòng.
        prompt_template = load_prompt("lead_qualifier")
        full_prompt = build_qualifier_prompt(
            prompt_template,
            inquiry_text,
            profession,
            scam_hint,
        )

        try:
            response = await self.provider.generate(
                prompt=full_prompt,
                temperature=0,
                seed=42,
                json_mode=True,
            )

            self.last_usage = response.usage

            result = self._parse_output(response.text)

            # Truy nguồn: bản ghi này sinh ra bởi prompt phiên bản nào.
            result["prompt_version"] = prompt_version("lead_qualifier")

            return result

        except Exception as exc:
            log.error(
                "ai.lead_qualifier.failed",
                error=str(exc),
            )
            raise