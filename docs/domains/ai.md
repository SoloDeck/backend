# AI Domain

## Purpose

Provide AI-powered generation capabilities that augment a freelancer's workflow — qualifying leads, drafting proposals, generating contracts, and composing follow-up messages. The AI domain is a service domain: it accepts structured inputs from business domains, invokes LLM chains, and returns structured outputs. It does not own business entities or modify data directly.

## Responsibilities

- Accept structured generation requests from business domains via the AIFacade
- Orchestrate LangChain chains for each generation task
- Manage prompt templates and system instructions per use case
- Parse and validate LLM outputs into typed structures
- Track AI generation requests and usage for cost accounting
- Enforce entitlement checks (subscription tier allows AI) before consuming tokens
- Log generation results for debugging and quality improvement
- Return structured outputs to the calling domain; never write to business tables directly

## Does Not Own

- Business entities: deals, proposals, contracts, clients (owned by their respective domains)
- Subscription entitlement enforcement beyond the initial check (owned by **Subscriptions** domain)
- Final content persistence (caller domain owns the write)
- Email delivery or notification dispatch (owned by **Workers** and **Reminders** domains)
- AI cost records storage (written to **Admin** domain's cost ledger)

## Core Concepts

**AIFacade** — The single public interface through which all business domains access AI capabilities. Business services call `AIFacade` methods; they never instantiate LangChain chains directly. Enforces a consistent contract and centralizes error handling.

**AI Module** — A self-contained LangChain chain implementation for one generation task. Each module lives under `src/ai/<module_name>/` and has its own prompt template, output parser, and unit tests.

**AI Modules:**

| Module | Input | Output |
|---|---|---|
| `lead_qualifier` | Deal data, client data, description | `QualificationResult`: score (0–100), recommendation (`qualify` \| `pass`), reasoning |
| `proposal_generator` | Deal data, client data, user professional profile, optional template | `ProposalDraft`: structured proposal content object |
| `contract_generator` | Deal data, accepted proposal content, client data, user profile | `ContractDraft`: structured contract content object |
| `followup_generator` | Deal data, client data, communication history, reminder type | `FollowUpDraft`: suggested message text |

**Generation Request** — An immutable record of an AI call: `request_id`, `user_id`, `module`, `model`, `input_hash`, `status` (`pending` | `completed` | `failed`), `created_at`, `completed_at`.

**Generation Result** — The structured output returned by a module. Typed per module (see table above). Stored temporarily; the calling domain decides whether and where to persist it.

**Prompt Template** — A versioned, parameterized instruction set fed to the LLM. Templates are stored under `src/ai/<module>/prompts/` and version-controlled. Changing a prompt template requires a version bump and test validation.

**Output Parser** — A Pydantic model that validates and structures raw LLM JSON output. If parsing fails, the module returns a `failed` result with the raw output for debugging.

## Business Rules

- All AI generation requests **must** pass through `AIFacade`. No business module may import LangChain or call OpenAI directly.
- Before invoking any chain, `AIFacade` calls `SubscriptionsService.check_entitlement(user_id, "can_use_ai")`. A user without AI entitlement receives a structured error, and no tokens are consumed.
- AI modules **must not** write to any database table. They return data structures; the calling domain persists as appropriate.
- If an LLM call fails (timeout, rate limit, API error), the module catches the error, marks the generation as `failed`, and raises a typed `AIGenerationError` that the caller handles.
- Output parsing failures must not silently return malformed data. Return `failed` status with raw output preserved for inspection.
- All generation calls are logged to the AI Cost ledger (via Admin domain event) regardless of outcome, for cost tracking.
- Input data passed to AI modules must not include sensitive financial data beyond what is necessary for generation (e.g. no bank account numbers).
- AI-generated content is always returned as a `draft`. The user must explicitly confirm or edit before it is used in a business action (send, activate).

## Lifecycle

```
[Business Domain calls AIFacade.generate_*(params)]
                 │
   Entitlement check (Subscriptions)
                 │
           ┌─────┴──────┐
           ▼            ▼
      [Allowed]     [Blocked]
           │            │
           │    Return AIEntitlementError
           │
  [Generation Request created: pending]
           │
   Invoke LangChain chain
           │
     ┌─────┴──────┐
     ▼            ▼
[LLM responds] [Timeout / Error]
     │                │
Output parsed    [status: failed]
     │            Return AIGenerationError
     ▼
[status: completed]
     │
Return structured output to caller
     │
[Caller domain persists as draft in its own table]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Subscriptions** | AI checks entitlement before every generation. Subscriptions owns the entitlement decision. |
| **Deals** | Lead Qualifier and Proposal/Contract Generators consume Deal data as input. Deals call AI via AIFacade. |
| **Proposals** | Proposal Generator produces a `ProposalDraft` written back to Proposals domain as a draft. |
| **Contracts** | Contract Generator produces a `ContractDraft` written back to Contracts domain as a draft. |
| **Reminders** | Follow-up Generator produces message text used as the `message_preview` in a Reminder. |
| **Clients** | AI modules consume Client data (name, industry, communication history) as generation context. |
| **Users** | AI modules consume User professional profile (skills, specialization, rate) as generation context. |
| **Admin** | AI Cost Records are emitted to Admin for cost monitoring and billing reconciliation. |
| **Workers** | Long-running AI generation jobs may be dispatched as Celery tasks via `ai_jobs/` workers. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `ai.generation_completed` | Module returns successful output | Caller domain (apply draft to entity), Admin (cost record) |
| `ai.generation_failed` | Module returns failed status | Caller domain (surface error to user), Admin (error log) |
| `ai.entitlement_blocked` | User lacks AI entitlement | Subscriptions (upsell event), Analytics |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Trigger AI generation on own business entities (subject to subscription entitlement) |
| **Admin** | View AI usage logs and cost records; cannot trigger generation on behalf of users |
| **Anonymous** | None |
| **Internal Services** | Business domain services call AIFacade with system-level credentials; not user-facing |

## Future Considerations

- Model selection per use case: allow users or admins to choose between GPT-4o, Claude, or Gemini per module
- Streaming responses: return generated content token-by-token to the frontend for a better UX
- Fine-tuned models: train on anonymized (user-consented) successful proposals to improve quality
- AI-assisted deal coaching: proactive suggestions on how to advance a stalled deal
- Multi-language support: generate content in Vietnamese or English based on user/client preference
- RAG (Retrieval-Augmented Generation): inject user's past winning proposals as context for new generations
- Feedback loop: user rates generated content (thumbs up/down) to improve prompt quality over time
- Cost budget per user: alert or block AI usage when a user's estimated monthly AI cost exceeds a threshold
