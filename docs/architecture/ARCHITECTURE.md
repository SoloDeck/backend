# SoloDesk Backend Architecture

## Top-Level Structure

src/

├── modules/
├── ai/
├── workers/
├── integrations/
├── infrastructure/
├── shared/
├── tests/

---

## Core Domains


### Auth

Authentication and authorization.

### Users

Responsibilities:

* User profile
* Authentication
* Google OAuth

### Subscriptions

Subscription plans and billing entitlements.

### Clients

Responsibilities:

* Client management
* Contact history

### Deals

Responsibilities:

* Lead intake
* Pipeline management

Pipeline stages:

1. New Lead
2. Qualified
3. Proposal Sent
4. In Negotiation
5. Active
6. Completed & Billed

### Contracts

Responsibilities:

* Contract generation
* Contract storage

### Reminders

Responsibilities:

* Payment reminders
* Re-engagement reminders

### Analytics

Responsibilities:

* Revenue metrics
* Win rate calculations

---

## AI Domain

Contains:

* Lead Qualifier
* Proposal Generator
* Contract Generator
* Follow-up Generator

Structure:

ai/

├── lead_qualifier/
├── proposal_generator/
├── contract_generator/
├── followup_generator/
└── shared/

---

## Worker Domain

Long-running jobs execute through Celery.

Examples:

AI generation
PDF generation
Email delivery
Zalo delivery
Scheduled reminders

workers/

├── ai_jobs/
├── pdf_jobs/
├── reminder_jobs/
└── scheduler/

All long-running jobs must execute through Celery.

## External Integrations
OpenAI
SendGrid
Zalo OA
Google OAuth
MoMo
Redis
PostgreSQL

Business modules must communicate through adapters located in integrations/.