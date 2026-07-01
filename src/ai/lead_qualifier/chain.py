"""LeadQualifier Groq chain."""

import asyncio
import json
import os
from typing import Any

import structlog
from groq import Groq

from src.ai.shared.base import BaseAIChain
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"
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
                raw=raw,
                error=str(exc),
            )
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
            temperature=0.2,
        )

        return response.choices[0].message.content or ""

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        inquiry_text = kwargs.get("inquiry_text")
        if not inquiry_text:
            raise ValueError("inquiry_text is required for LeadQualifier")

        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "prompts",
            "prompts.txt",
        )

        try:
            with open(prompt_path, encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            prompt_template = (
                "Qualify the following lead as JSON with keys: "
                "score (0-100), qualified (bool), reasoning (str)."
            )

        full_prompt = f"""{prompt_template}

Client Inquiry:
{inquiry_text}
"""

        try:
            raw_response = await asyncio.to_thread(
                self._call_groq,
                full_prompt,
            )

            return self._parse_output(raw_response)

        except Exception as exc:
            log.error(
                "ai.lead_qualifier.failed",
                error=str(exc),
            )
            raise