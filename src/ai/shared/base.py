"""Base class for all AI chain modules."""

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import settings
from src.shared.exceptions.domain import AIGenerationError, AIOutputParseError

log = structlog.get_logger()


class BaseAIChain(ABC):
    """Abstract base for LangChain-backed AI modules.

    Subclasses implement `_build_chain()` and `_parse_output()`.
    `run()` handles retries, logging, and error wrapping.
    """

    module_name: str  # must be set on each subclass

    @abstractmethod
    def _build_chain(self) -> Any: ...

    @abstractmethod
    def _parse_output(self, raw: str) -> dict[str, Any]: ...

    @retry(
        stop=stop_after_attempt(settings.openai_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def run(self, **kwargs: Any) -> dict[str, Any]:
        generation_id = uuid.uuid4()
        started_at = datetime.now(UTC)

        log.info(
            "ai.generation.started",
            module=self.module_name,
            generation_id=str(generation_id),
        )
        try:
            chain = self._build_chain()
            raw_output: str = await chain.ainvoke(kwargs)
            result = self._parse_output(raw_output)
            result["generation_id"] = generation_id
            log.info(
                "ai.generation.completed",
                module=self.module_name,
                generation_id=str(generation_id),
                duration_ms=(datetime.now(UTC) - started_at).total_seconds() * 1000,
            )
            return result
        except AIOutputParseError:
            raise
        except Exception as exc:
            log.error(
                "ai.generation.failed",
                module=self.module_name,
                generation_id=str(generation_id),
                error=str(exc),
            )
            raise AIGenerationError(f"{self.module_name} generation failed: {exc}") from exc
