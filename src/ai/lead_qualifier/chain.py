"""LeadQualifier Gemini chain — implementing Gemini 2.0+ SDK."""
import json
import os
from typing import Any

import structlog
from google import genai

from src.ai.shared.base import BaseAIChain
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"
    _client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is not None:
            return self._client

        api_key = settings.google_api_key
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set in settings")

        self._client = genai.Client(api_key=api_key)
        return self._client

    def set_client_for_tests(self, client: Any) -> None:
        """ONLY used in unit tests"""
        self._client = client

    def _build_chain(self) -> Any:
        """Not used for direct Gemini SDK implementation, but required by BaseAIChain."""
        return None

    def _parse_output(self, raw: str) -> dict[str, Any]:
        try:
            # Clean potential Markdown formatting
            text = raw.strip()
            if text.startswith("```json"):
                text = text.removeprefix("```json")
            if text.endswith("```"):
                text = text.removesuffix("```")
            text = text.strip()
            
            return json.loads(text)
        except json.JSONDecodeError as exc:
            log.error("ai.lead_qualifier.parse_failed", raw=raw, error=str(exc))
            raise AIOutputParseError(f"Failed to parse lead qualification output: {exc}", raw_output=raw)

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """Override run to use direct Gemini SDK instead of LangChain."""
        inquiry_text = kwargs.get("inquiry_text")
        if not inquiry_text:
            raise ValueError("inquiry_text is required for LeadQualifier")

        client = self._get_client()
        
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "prompts",
            "prompts.txt"
        )

        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            # Fallback if prompts.txt is missing during refactor
            prompt_template = "Qualify the following lead as JSON with keys: score (0-100), qualified (bool), reasoning (str)."

        full_prompt = f"""{prompt_template}

Client Inquiry:
{inquiry_text}
"""

        try:
            # Using the Gemini SDK directly (async)
            response = await client.aio.models.generate_content(
                model="gemma-4-31b-it",
                contents=full_prompt,
            )
            
            result = self._parse_output(response.text)
            return result
        except Exception as exc:
            log.error("ai.lead_qualifier.failed", error=str(exc))
            raise
