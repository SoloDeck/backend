"""ContractGenerator Groq chain."""

import asyncio
import json
import os
from typing import Any

import structlog
from groq import Groq

from src.ai.contract_generator.schemas.contract_content import (
    ContractClauses,
    build_parties,
)
from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()

# openapi.yaml khai ContractContentDTO.governing_law có default là "Vietnam".
# Đây là hằng số, không phải thứ để model đoán.  #Huynh
GOVERNING_LAW = "Vietnam"


class ContractGenerator(BaseAIChain):
    """Sinh điều khoản hợp đồng bằng Groq.

    File này trước đây là khung rỗng: cả _build_chain lẫn _parse_output đều
    `raise NotImplementedError`, kèm TODO bảo dựng LangChain chain. Tôi không đi
    đường đó — không module AI nào trong repo làm vậy cả (lead_qualifier kế thừa
    BaseAIChain nhưng override luôn run() và gọi thẳng Groq; proposal_generator
    thậm chí không kế thừa). Đi đường LangChain là dựng lại từ đầu một kiến trúc
    chưa ai chạy thật, và lãnh lại đúng mấy lỗi parse JSON đã sửa xong.  #Huynh
    """

    module_name = "contract_generator"
    _client: Groq | None = None

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
            log.error("ai.contract_generator.parse_failed", raw=raw, error=str(exc))
            raise AIOutputParseError(
                f"Failed to parse contract generation output: {exc}",
                raw_output=raw,
            ) from exc

    def _call_groq(self, full_prompt: str) -> str:
        """Gọi Groq (blocking) — chạy trong worker thread."""
        client = self._get_client()

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": full_prompt}],
            # Hợp đồng là văn bản pháp lý: cần bám sát dữ liệu, không cần "sáng tạo".
            # Để thấp hơn báo giá (0.2) cho model bớt tự bịa điều khoản.  #Huynh
            temperature=0.1,
            # Buộc API trả JSON thuần. Thiếu cờ này llama-4-scout bọc câu trả lời trong
            # văn bản dẫn nhập và parser vỡ — đúng con bug đã làm chết lead_qualifier.
            response_format={"type": "json_object"},
        )

        return response.choices[0].message.content or ""

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        deal_data: dict[str, Any] = kwargs.get("deal_data") or {}
        proposal_content: dict[str, Any] = kwargs.get("proposal_content") or {}
        client_data: dict[str, Any] = kwargs.get("client_data") or {}
        user_profile: dict[str, Any] = kwargs.get("user_profile") or {}

        system_prompt = self._load_system_prompt()

        full_prompt = f"""{system_prompt}

## Thông tin dự án
{json.dumps(deal_data, ensure_ascii=False, indent=2)}

## Báo giá khách đã chấp nhận
{json.dumps(proposal_content, ensure_ascii=False, indent=2)}

## Khách hàng
{json.dumps(client_data, ensure_ascii=False, indent=2)}

## Freelancer
{json.dumps(user_profile, ensure_ascii=False, indent=2)}
"""

        try:
            raw_response = await asyncio.to_thread(self._call_groq, full_prompt)
            clauses = ContractClauses.model_validate(self._parse_output(raw_response))

            # Ghép thành đủ 8 trường của ContractContentDTO: 6 điều khoản do AI viết,
            # còn parties và governing_law thì code tự điền từ DB.  #Huynh
            return {
                **clauses.model_dump(),
                "parties": build_parties(client_data, user_profile),
                "governing_law": GOVERNING_LAW,
            }

        except Exception as exc:
            log.error("ai.contract_generator.failed", error=str(exc))
            raise

    def _load_system_prompt(self) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system.txt")
        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            log.warning("ai.contract_generator.prompt_missing", path=prompt_path)
            return (
                "Soạn điều khoản hợp đồng dịch vụ bằng tiếng Việt. Trả JSON với các khóa: "
                "scope_of_work, payment_terms, revision_policy, ip_ownership, "
                "termination_clause, custom_clauses. Mọi giá trị là chuỗi."
            )
