from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.shared.llm_provider import (
    BaseLLMProvider,
    get_llm_provider,
)
from src.modules.admin.infrastructure.repository import AdminRepository

class ProviderFactory:
    def __init__(self, db: AsyncSession):
        self.repo = AdminRepository(db)

    async def get_provider(self) -> BaseLLMProvider:
        configuration = await self.repo.get_ai_provider_configuration()

        if configuration is None:
            raise RuntimeError("AI provider configuration not found")

        return get_llm_provider(configuration.llm_provider)