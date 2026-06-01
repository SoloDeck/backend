# Naming Rules

## General Conventions

| Convention | Applies To |
|-----------|-----------|
| `snake_case` | Variables, functions, methods, module names, file names |
| `PascalCase` | Classes, Pydantic models, domain entities, SQLAlchemy models |
| `UPPER_SNAKE_CASE` | Constants, Enum values |
| `kebab-case` | URLs, file names in `docs/` |

---

## Service Naming

Pattern: `<Domain>Service`

```python
AuthService
UsersService
DealsService
ProposalsService
ContractsService
InvoicesService
RemindersService
SubscriptionsService
ClientsService
AnalyticsService
AdminService
```

Service method names use imperative verbs:

```python
# CORRECT
async def create_deal(...)
async def transition_stage(...)
async def qualify_with_ai(...)
async def generate_proposal(...)
async def send_invoice(...)
async def cancel_reminder(...)

# WRONG
async def deal_create(...)
async def stage_transition(...)
async def get_ai_qualification(...)
```

---

## Repository Naming

Pattern: `<Domain>Repository`

```python
AuthRepository
UsersRepository
DealsRepository
ClientsRepository
```

Repository method names describe the query, not the action:

```python
# CORRECT — describe what is returned
async def get_by_id(...)
async def get_by_email(...)
async def list_by_owner(...)
async def get_active_by_deal_id(...)
async def count_by_status(...)

# WRONG — imperative (belongs in service)
async def create_and_save(...)
async def find_or_raise(...)
```

---

## Schema (DTO) Naming

Requests: `<Action><Domain>Request`

```python
CreateDealRequest
UpdateDealRequest
StageTransitionRequest
RegisterRequest
LoginRequest
GenerateProposalRequest
```

Responses: `<Domain>Response` or `<Domain>Page`

```python
DealResponse
DealPage              # paginated list
UserResponse
AuthTokenResponse
LeadQualificationResponse
```

---

## Domain Entity Naming

Entities match the domain aggregate root exactly:

```python
User
Deal
Client
Proposal
Contract
Invoice
Reminder
Subscription
```

Value objects use descriptive noun phrases:

```python
ProfessionalProfile
Preferences
DealActivityEntry
ClientSnapshot
BillingPeriod
```

---

## Event Naming

Pattern: `<domain>.<past_tense_verb>`

```python
users.user_created
users.user_deleted
deals.stage_transitioned
deals.deal_closed
proposals.proposal_accepted
proposals.proposal_expired
contracts.milestone_reached
invoices.invoice_paid
invoices.invoice_overdue
reminders.reminder_delivered
subscriptions.plan_changed
```

---

## SQLAlchemy Model Naming

Pattern: `<Domain>Model` — never shadow the domain entity name.

```python
UserModel         # entity: User
DealModel         # entity: Deal
ClientModel       # entity: Client
ProposalModel     # entity: Proposal
ContractModel     # entity: Contract
InvoiceModel      # entity: Invoice
ReminderModel     # entity: Reminder
SubscriptionModel # entity: Subscription
PlanModel         # entity: SubscriptionPlan
```

---

## File Naming

| File | Name |
|------|------|
| Router | `router.py` |
| Service | `service.py` |
| Domain entities | `entities.py` |
| ORM models | `models.py` |
| Repository | `repository.py` |
| Inbound schemas | `request.py` |
| Outbound schemas | `response.py` |
| AI chain | `chain.py` |
| System prompt | `system.txt` |

---

## URL Path Naming

- Lowercase, hyphen-separated: `/api/v1/deals`, `/api/v1/password-reset/request`
- Resource IDs as path params: `/deals/{deal_id}`
- Actions as sub-paths: `/deals/{deal_id}/stage-transition`
- No verbs in resource paths (except action sub-paths): `/deals` not `/get-deals`
