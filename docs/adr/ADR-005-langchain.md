# ADR-005: LangChain for AI Orchestration

**Status:** Accepted

---

## Context

SoloDesk's core differentiator is AI automation: lead qualification, proposal generation, contract generation, and follow-up message generation. Each of these requires prompt templating, structured output parsing, and retry logic around LLM calls. A decision on whether to use a framework or call the OpenAI API directly was needed.

## Problem

Should we use a framework for LLM orchestration or call the OpenAI API directly?

## Decision

Use **LangChain** (`langchain` + `langchain-openai`) for AI chain construction.

- All AI logic lives exclusively in `src/ai/`.
- Each capability is a separate chain module: `lead_qualifier/`, `proposal_generator/`, `contract_generator/`, `followup_generator/`.
- A shared `BaseAIChain` ABC in `src/ai/shared/base.py` provides retry logic (via `tenacity`), structured logging, and error wrapping.
- Chains return plain `dict` output — never ORM models or domain entities. The calling service writes results to the database.
- Prompt templates are stored in `src/ai/<module>/prompts/system.txt` — versioned in git, editable without code changes.
- LangChain is **never imported from `src/modules/`** — all access goes through `AIFacade`.

## Alternatives Considered

| Alternative | Reason Rejected |
|-------------|-----------------|
| Raw OpenAI SDK only | More verbose; no built-in prompt templating or output parsing; retry logic must be re-implemented |
| Instructor (structured outputs) | Good for parsing but not a full chain framework; complementary, not a replacement |
| LlamaIndex | Optimized for RAG / document retrieval; overkill for generation tasks |
| Haystack | Enterprise-focused; heavier than needed; less Python-native feel |
| DSPy | Experimental; less production tooling; not well-known by most agents |

## Consequences

**Positive:**
- Prompt templates, output parsers, and chain composition in one place.
- `LCEL` (LangChain Expression Language) enables clean pipeline definition.
- Easy to swap models (GPT-4o → Claude → Gemini) by changing the LLM constructor.
- Prompt versioning in `.txt` files allows non-engineer prompt iteration.

**Negative:**
- LangChain's API changes frequently — pin versions tightly.
- Abstraction overhead: debugging a failing chain requires understanding multiple layers.
- Token counting and cost tracking must be wired manually via callbacks (handled in `BaseAIChain`).
- The `langchain` package is large — cold Docker build time increases.
