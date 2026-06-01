# Domain Documentation Generation Task

Generate complete domain documentation for SoloDesk.

Purpose:

Create business-oriented domain documents that will be used as the single source of truth for:

* Database design
* API design
* Service implementation
* AI-assisted code generation
* Future maintenance

Do NOT generate code.

Only generate domain documentation.

---

## Output Location

docs/domains/

Create:

* auth.md
* users.md
* subscriptions.md
* clients.md
* deals.md
* proposals.md
* contracts.md
* invoices.md
* reminders.md
* analytics.md
* admin.md
* ai.md

---

## Required Structure For Every Domain

# Domain Name

## Purpose

Why this domain exists.

## Responsibilities

List responsibilities owned by this domain.

## Does Not Own

List responsibilities belonging to other domains.

## Core Concepts

Important business concepts.

## Business Rules

Business constraints and invariants.

## Lifecycle

Describe state transitions if applicable.

## Relationships

Describe relationships with other domains.

## Events

Domain events that may be published.

## Permissions

Role-based access rules.

## Future Considerations

Potential future extensions.

---

## SoloDesk Specific Guidance

### Auth

Responsibilities:

* Login
* Logout
* JWT
* OAuth

---

### Users

Responsibilities:

* Profile management
* Preferences
* Professional profile

---

### Subscriptions

Responsibilities:

* Plan management
* Entitlements
* Usage limits

Business Rules:

* AI generation requires active subscription.
* Usage limits depend on subscription tier.

---

### Clients

Responsibilities:

* Client records
* Contact information
* Communication history

Business Rules:

* Every Deal belongs to one Client.
* Client may have multiple Deals.

---

### Deals

Responsibilities:

* Lead intake
* Pipeline management

Pipeline Stages:

1. New Lead
2. Qualified
3. Proposal Sent
4. In Negotiation
5. Active
6. Completed & Billed

Business Rules:

* Stage transitions must be validated.
* Completed deals contribute to revenue analytics.

---

### Proposals

Responsibilities:

* Proposal generation
* Proposal versioning

Business Rules:

* Proposal belongs to a Deal.
* Multiple revisions allowed.

---

### Contracts

Responsibilities:

* Contract generation
* Contract storage

Business Rules:

* Contract generated from accepted Proposal.
* Contract must reference Client and Deal.

---

### Invoices

Responsibilities:

* Billing
* Payment tracking

Business Rules:

* Invoice belongs to Contract.
* Invoice may be unpaid, partially paid or paid.

---

### Reminders

Responsibilities:

* Follow-up reminders
* Payment reminders

Business Rules:

* Reminder may target Client, Deal or Invoice.
* Reminder execution handled by Workers.

---

### Analytics

Responsibilities:

* Revenue reporting
* Win rate reporting
* Pipeline metrics

Business Rules:

* Analytics data derived from operational domains.
* No direct ownership of business entities.

---

### Admin

Responsibilities:

* User administration
* Template management
* AI cost monitoring
* Subscription management

---

### AI

Responsibilities:

* Lead Qualification
* Proposal Generation
* Contract Generation
* Follow-up Generation

Business Rules:

* AI modules never modify database directly.
* AI modules return structured outputs.
* AI modules are orchestrated through AIFacade.

---

## Expected Outcome

After completion:

1. Every business domain has clear ownership.
2. Domain boundaries are documented.
3. Database design can be derived from domain documents.
4. API design can be derived from domain documents.
5. AI coding agents can implement features without guessing business rules.

Do not create implementation details.

Focus on business domain modeling and domain boundaries only.
