"""FollowUpGenerator LangChain chain — skeleton."""
from typing import Any

from src.ai.shared.base import BaseAIChain


class FollowUpGenerator(BaseAIChain):
    module_name = "followup_generator"

    def _build_chain(self) -> Any:
        # TODO: build LangChain chain using prompt templates + LLM + output parser
        raise NotImplementedError

    def _parse_output(self, raw: str) -> dict[str, Any]:
        # TODO: validate and structure raw LLM output via Pydantic parser
        raise NotImplementedError
