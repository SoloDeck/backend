"""LeadQualifier Groq chain."""

import asyncio
import json
from typing import Any

import structlog
from groq import Groq

from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt, prompt_version
from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"
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
        """Bóc khối JSON ra khỏi câu trả lời của model.

        Phần bóc nằm ở ``src/ai/shared/json_output.py`` để proposal_generator dùng
        chung — trước đây mỗi chain một bản, sửa nơi này quên nơi kia.  #Huynh
        """
        try:
            return extract_json_object(raw)
        except json.JSONDecodeError as exc:
            log.error("ai.lead_qualifier.parse_failed", raw=raw, error=str(exc))
            raise AIOutputParseError(
                f"Failed to parse lead qualification output: {exc}",
                raw_output=raw,
            ) from exc

    def _call_groq(self, full_prompt: str) -> str:
        """Blocking Groq API call executed in a worker thread."""
        client = self._get_client()

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            # Chấm điểm phải LẶP LẠI ĐƯỢC. Ở 0.2, chấm cùng một deal hai lần ra 70 rồi 52
            # — cùng dữ liệu, khác kết quả. Không ai tin nổi một thang điểm như thế, và khi
            # bảo vệ đồ án mà chấm lại ra số khác là hỏng.
            #
            # 0 không đảm bảo tuyệt đối giống nhau (model vẫn có sai số nội tại), nhưng loại
            # bỏ phần ngẫu nhiên do ta tự thêm vào. Các module khác (soạn hợp đồng 0.1, viết
            # tin nhắn nhắc 0.3) thì cần chút biến thiên vì đó là VIẾT VĂN — còn đây là ĐO
            # LƯỜNG.  #Huynh
            temperature=0,
            # Cùng đầu vào -> cùng đầu ra, kể cả khi Groq gom batch khác nhau giữa hai lần
            # gọi. Chỉ temperature=0 thôi vẫn thấy chấm 70 rồi 80 trên cùng một deal.  #Huynh
            seed=42,
            # Buộc model trả JSON thuần. Thiếu cờ này, llama-4-scout bọc câu trả lời
            # trong văn bản ("Here is the draft qualification result:") và parser vỡ.
            # Prompt vốn đã yêu cầu trả JSON, nhưng chỉ cờ này mới khiến API BẢO ĐẢM
            # điều đó.  #Huynh
            response_format={"type": "json_object"},
        )

        self.last_usage = extract_usage(response, model=getattr(response, "model", None) or MODEL)

        return response.choices[0].message.content or ""

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        inquiry_text = kwargs.get("inquiry_text")
        if not inquiry_text:
            raise ValueError("inquiry_text is required for LeadQualifier")

        # KHÔNG có prompt dự phòng. Trước đây thiếu file thì rơi về một prompt rác 2 dòng
        # ("Qualify the following lead as JSON...") và hệ thống VẪN CHẤM ĐIỂM — sai bét mà
        # không ai biết. Thà nổ to còn hơn âm thầm chấm sai.  #Huynh
        prompt_template = load_prompt("lead_qualifier")

        full_prompt = f"""{prompt_template}

Client Inquiry:
{inquiry_text}
"""

        try:
            raw_response = await asyncio.to_thread(
                self._call_groq,
                full_prompt,
            )

            result = self._parse_output(raw_response)
            # Truy nguồn: bản ghi này sinh ra bởi prompt phiên bản nào.  #Huynh
            result["prompt_version"] = prompt_version("lead_qualifier")
            return result

        except Exception as exc:
            log.error(
                "ai.lead_qualifier.failed",
                error=str(exc),
            )
            raise
