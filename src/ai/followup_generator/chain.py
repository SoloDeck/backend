"""FollowUpGenerator Groq chain."""

import asyncio
import json
from typing import Any

import structlog
from groq import Groq

from src.ai.followup_generator.schemas.followup import FollowUpMessage
from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt
from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class FollowUpGenerator(BaseAIChain):
    """Soạn tin nhắn nhắc khách bằng Groq.

    File này trước đây là khung rỗng (`raise NotImplementedError` + TODO dựng LangChain
    chain). Tôi không đi đường đó — không module AI nào trong repo làm vậy, và đó là
    kiến trúc chưa ai chạy thật. Chép khuôn lead_qualifier/contract_generator: gọi thẳng
    Groq, bật JSON mode, dùng chung ``extract_json_object``.  #Huynh
    """

    module_name = "followup_generator"
    _client: Groq | None = None
    # Token của lần gọi gần nhất — service đọc để ghi vào ai_cost_records.
    last_usage: dict[str, Any] | None = None

    def _get_client(self) -> Groq:
        if self._client is not None:
            return self._client

        api_key = settings.groq_api_key
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in settings")

        self._client = Groq(api_key=api_key)
        return self._client

    def set_client_for_tests(self, client: Any) -> None:
        """ONLY used in unit tests."""
        self._client = client

    def _build_chain(self) -> Any:
        """Required by BaseAIChain."""
        return None

    def _parse_output(self, raw: str) -> dict[str, Any]:
        try:
            return extract_json_object(raw)
        except json.JSONDecodeError as exc:
            log.error("ai.followup_generator.parse_failed", raw=raw, error=str(exc))
            raise AIOutputParseError(
                f"Failed to parse follow-up output: {exc}",
                raw_output=raw,
            ) from exc

    def _call_groq(self, full_prompt: str) -> str:
        client = self._get_client()

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": full_prompt}],
            # Tin nhắn gửi cho khách: cần bám dữ liệu, không cần "sáng tạo". Nhưng để
            # thấp như contract_generator (0.1) thì tin nhắn cứng đờ, đọc như văn mẫu.
            # 0.3 là mức tự nhiên mà vẫn không bịa thêm chi tiết.  #Huynh
            temperature=0.3,
            # Thiếu cờ này llama-4-scout bọc JSON trong văn bản dẫn nhập và parser vỡ —
            # đúng con bug đã làm chết lead_qualifier.
            response_format={"type": "json_object"},
        )

        self.last_usage = extract_usage(response, model=getattr(response, "model", None) or MODEL)

        return response.choices[0].message.content or ""

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        reminder_type: str = kwargs.get("reminder_type") or "follow_up"
        deal_data: dict[str, Any] = kwargs.get("deal_data") or {}
        client_data: dict[str, Any] = kwargs.get("client_data") or {}
        history: list[dict[str, Any]] = kwargs.get("communication_history") or []

        system_prompt = self._load_system_prompt()

        full_prompt = f"""{system_prompt}

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
            raw_response = await asyncio.to_thread(self._call_groq, full_prompt)
            message = FollowUpMessage.model_validate(self._parse_output(raw_response))
            return message.model_dump()

        except Exception as exc:
            log.error("ai.followup_generator.failed", error=str(exc))
            raise

    def _load_system_prompt(self) -> str:
        # KHÔNG có prompt dự phòng. Trước đây thiếu file thì rơi về vài dòng viết vội và hệ
        # thống VẪN CHẠY — soạn ra một văn bản gửi cho khách hàng thật, bằng một prompt
        # không ai rà soát. Thà nổ to lúc khởi động còn hơn.  #Huynh
        return load_prompt("followup_generator")
