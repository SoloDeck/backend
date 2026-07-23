"""LeadQualifier Groq Chain."""

import asyncio
import json
from typing import Any

import structlog
from groq import Groq

from src.ai.lead_qualifier.prompt_builder import (
    LeadQualificationPromptBuilder,
)
from src.ai.lead_qualifier.retriever import (
    LeadQualificationRetriever,
)
from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"

    _client: Groq | None = None

    # Loaded once for the application's lifetime
    _retriever = LeadQualificationRetriever()
    _prompt_builder = LeadQualificationPromptBuilder()

    # ---------------------------------------------------------
    # Groq Client
    # ---------------------------------------------------------

    def _get_client(self) -> Groq:

        if self._client is not None:
            return self._client

        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        self._client = Groq(
            api_key=settings.groq_api_key,
        )

        return self._client

    def set_client_for_tests(self, client: Any) -> None:
        self._client = client

    def _build_chain(self) -> Any:
        return None

    # ---------------------------------------------------------
    # Output Parser
    # ---------------------------------------------------------

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
                f"Unable to parse LeadQualifier output: {exc}",
                raw_output=raw,
            ) from exc

    # ---------------------------------------------------------
    # LLM Call
    # ---------------------------------------------------------

    def _call_groq(
        self,
        prompt: str,
    ) -> str:

        client = self._get_client()

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.2,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            # Buộc model trả JSON thuần. Thiếu cờ này, llama-4-scout bọc câu trả lời
            # trong văn bản ("Here is the draft qualification result:") và parser vỡ.
            # Prompt vốn đã yêu cầu trả JSON, nhưng chỉ cờ này mới khiến API BẢO ĐẢM
            # điều đó.  #Huynh
            response_format={"type": "json_object"},
        )

        return response.choices[0].message.content or ""

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    async def run(
        self,
        *,
        profession: str | None,
        inquiry_context: str,
    ) -> dict[str, Any]:

        if not inquiry_context:
            raise ValueError("inquiry_context is required")

        # Retrieve framework + profession knowledge
        retrieved_knowledge = self._retriever.retrieve(
            profession=profession,
            query=inquiry_context,
        )

        # Build prompt
        full_prompt = self._prompt_builder.build(
            profession=profession,
            inquiry_context=inquiry_context,
            retrieved_knowledge=retrieved_knowledge,
        )

        try:

            raw = await asyncio.to_thread(
                self._call_groq,
                full_prompt,
            )

            return self._parse_output(raw)

        except Exception as exc:

            log.error(
                "ai.lead_qualifier.failed",
                error=str(exc),
            )

            raise
