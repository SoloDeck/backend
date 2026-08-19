"""FollowUpGenerator AI chain."""

import json
from typing import Any

import structlog

from src.ai.followup_generator.schemas.followup import FollowUpMessage
from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()


# Hai giọng theo Phiếu SU26SE083 (dòng 105: "chọn được giọng trang trọng hoặc thân mật").
#
# Tả bằng ĐẶC ĐIỂM CỤ THỂ (xưng hô, độ dài câu, có được dùng cảm thán không) chứ không chỉ
# ghi "trang trọng"/"thân mật": model hiểu hai chữ đó rất khác nhau giữa các lần gọi, và
# freelancer thì phải nhận ra được sự khác biệt ngay khi bấm đổi giọng.
TONE_INSTRUCTIONS: dict[str, str] = {
    "formal": (
        "TRANG TRỌNG. Xưng 'chúng tôi' hoặc tên riêng, gọi khách là 'Quý khách' hoặc "
        "'Anh/Chị'. Câu đầy đủ chủ vị, không viết tắt, không cảm thán, không emoji. "
        "Mở đầu bằng một câu lịch sự nêu lý do liên hệ, kết bằng lời cảm ơn. "
        "Dùng khi khách là công ty hoặc mới quen."
    ),
    "friendly": (
        "THÂN MẬT. Xưng 'mình'/'em', gọi khách là 'anh'/'chị' theo cách trò chuyện thường "
        "ngày. Câu ngắn, gần với lời nói, được dùng tối đa MỘT emoji ở cuối. Vẫn lịch sự và "
        "KHÔNG suồng sã, không tiếng lóng. Dùng khi đã làm việc với khách nhiều lần."
    ),
}


class FollowUpGenerator(BaseAIChain):
    """Generate follow-up messages using the configured LLM provider."""

    module_name = "followup_generator"

    # Token usage from the most recent generation.
    last_usage: dict[str, Any] | None = None

    def _build_chain(self) -> Any:
        """Required by BaseAIChain."""
        return None

    def _parse_output(self, raw: str) -> dict[str, Any]:
        try:
            return extract_json_object(raw)
        except json.JSONDecodeError as exc:
            log.error(
                "ai.followup_generator.parse_failed",
                raw=raw,
                error=str(exc),
            )
            raise AIOutputParseError(
                f"Failed to parse follow-up output: {exc}",
                raw_output=raw,
            ) from exc

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        reminder_type: str = kwargs.get("reminder_type") or "follow_up"
        deal_data: dict[str, Any] = kwargs.get("deal_data") or {}
        client_data: dict[str, Any] = kwargs.get("client_data") or {}
        history: list[dict[str, Any]] = kwargs.get("communication_history") or []
        tone: str = kwargs.get("tone") or "formal"

        system_prompt = self._load_system_prompt()

        full_prompt = f"""{system_prompt}

## GIỌNG VĂN BẮT BUỘC
{TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["formal"])}

## LOẠI NHẮC
{reminder_type}

## KHÁCH HÀNG
{json.dumps(client_data, ensure_ascii=False, indent=2)}

## BỐI CẢNH (dữ liệu THẬT — chỉ được dùng những gì có ở đây)
{json.dumps(deal_data, ensure_ascii=False, indent=2)}

## TRAO ĐỔI GẦN ĐÂY
{json.dumps(history, ensure_ascii=False, indent=2) if history else "(chưa có ghi nhận)"}
"""

        try:
            provider = await self.get_provider()

            response = await provider.generate(
                prompt=full_prompt,
                temperature=0.3,
                json_mode=True,
            )

            self.last_usage = response.usage

            message = FollowUpMessage.model_validate(
                self._parse_output(response.text)
            )

            return message.model_dump()

        except Exception as exc:
            log.error(
                "ai.followup_generator.failed",
                error=str(exc),
            )
            raise

    def _load_system_prompt(self) -> str:
        # KHÔNG có prompt dự phòng. Trước đây thiếu file thì rơi về vài dòng viết vội và hệ
        # thống VẪN CHẠY — soạn ra một văn bản gửi cho khách hàng thật, bằng một prompt
        # không ai rà soát. Thà nổ to lúc khởi động còn hơn.
        return load_prompt("followup_generator")
