# ADR-006: AIFacade Pattern for AI Access Control

**Status:** Accepted

---

## Context

AI calls are expensive (token cost), latency-sensitive, and require entitlement checks (only paid subscribers can use AI features). Without a controlled access point, LLM calls could be scattered across modules, making cost tracking, access control, and model swapping difficult.

## Problem

How do we ensure that AI features are always gated behind entitlement checks, cost is always recorded, and LangChain logic never leaks into business modules?

## Decision

Implement a single **`AIFacade`** class in `src/ai/facade.py` as the only permitted AI entry point for business modules.

- `AIFacade` is a dataclass injected into service constructors via FastAPI's `Depends()`.
- It holds references to all four AI chain instances: `LeadQualifier`, `ProposalGenerator`, `ContractGenerator`, `FollowUpGenerator`.
- Every public method on `AIFacade` calls `_check_entitlement()` first — raises `EntitlementError` if `can_use_ai=False`.
- All generation calls log to `ai_cost_records` regardless of success or failure.
- Methods return plain `dict` — never LangChain or OpenAI types.
- Business modules **never import** `langchain`, `openai`, or any chain class directly.

Enforcement rule (in `CLAUDE.md` and `AGENTS.md`):
```
# FORBIDDEN in src/modules/
from langchain_openai import ChatOpenAI
from src.ai.lead_qualifier.chain import LeadQualifierChain

# CORRECT
result = await self.ai_facade.qualify_lead(deal_data=..., client_data=..., user_can_use_ai=...)
```

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Call chains directly from services | No single enforcement point for entitlement; cost tracking scattered |
| AI module as a microservice | Network overhead; over-engineered for current scale |
| Chain injection per-service (not via facade) | Entitlement check could be forgotten; 4 chains × 11 services = 44 injection points |
| Middleware-level AI gate | Cannot access subscription data cleanly at middleware; business context not available |

## Consequences

**Positive:**
- Single enforcement point for entitlement checks — can never be bypassed accidentally.
- Cost recording centralized — always fires regardless of which module uses AI.
- Model swap (GPT-4o → GPT-4o-mini for cost optimization) requires changing one file.
- LangChain version upgrades are isolated to `src/ai/` — zero impact on business modules.
- Easy to mock in tests — inject a fake `AIFacade` into services.

**Negative:**
- `AIFacade` becomes a wide interface if many AI capabilities are added — consider splitting into domain-specific facades (e.g., `DealAIFacade`, `DocumentAIFacade`) when it exceeds 6–8 methods.
- Async chain execution is sequential within a single facade call — parallel generation (e.g., proposal + contract at once) requires explicit `asyncio.gather` inside the facade.
