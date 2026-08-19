"""ContractGenerator AI chain."""

import json
from typing import Any

import structlog

from src.ai.contract_generator.schemas.contract_content import (
    ContractClauses,
    build_parties,
)
from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()

# openapi.yaml declares ContractContentDTO.governing_law default as "Vietnam".
# This is a constant, not something the model should infer.
GOVERNING_LAW = "Vietnam"


class ContractGenerator(BaseAIChain):
    """Generate contract clauses using the configured LLM provider."""

    module_name = "contract_generator"

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
                "ai.contract_generator.parse_failed",
                raw=raw,
                error=str(exc),
            )
            raise AIOutputParseError(
                f"Failed to parse contract generation output: {exc}",
                raw_output=raw,
            ) from exc

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
            provider = await self.get_provider()

            response = await provider.generate(
                prompt=full_prompt,
                temperature=0.1,
                json_mode=True,

            )

            self.last_usage = response.usage

            clauses = ContractClauses.model_validate(
                self._parse_output(response.text)
            )

            # Assemble the full ContractContentDTO.
            return {
                **clauses.model_dump(),
                "parties": build_parties(client_data, user_profile),
                "governing_law": GOVERNING_LAW,
            }

        except Exception as exc:
            log.error(
                "ai.contract_generator.failed",
                error=str(exc),
            )
            raise

    def _load_system_prompt(self) -> str:
        # No fallback prompt. Missing prompts should fail loudly.
        return load_prompt("contract_generator")
