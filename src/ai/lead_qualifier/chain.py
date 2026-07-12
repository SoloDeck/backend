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

    def _parse_output(
        self,
        raw: str,
    ) -> dict[str, Any]:

        try:

            text = raw.strip()

            if text.startswith("```json"):
                text = text.removeprefix("```json").strip()

            elif text.startswith("```"):
                text = text.removeprefix("```").strip()

            if text.endswith("```"):
                text = text.removesuffix("```").strip()

            return json.loads(text)

        except json.JSONDecodeError as exc:

            log.error(
                "ai.lead_qualifier.parse_failed",
                error=str(exc),
                raw=raw,
            )

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