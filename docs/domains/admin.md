# Admin Domain

## Purpose

Provide platform operators with the tools to manage the SoloDesk system: oversee user accounts, monitor platform health, control content templates, audit activity, and manage AI infrastructure costs. Admin is a cross-cutting operational domain — it can read and act on data across all other domains but produces no first-class business entities of its own.

## Responsibilities

- User account administration (view, suspend, reinstate, delete, change role)
- Subscription management overrides (manually assign or override plans)
- Template management: create and manage system-level proposal and contract templates available to all users
- Monitor AI cost and usage across the platform
- View platform-wide audit logs
- Manage feature flags for gradual feature rollout
- View platform health metrics and error reports
- Handle support-related data lookups (access any user's records read-only)

## Does Not Own

- User profile data (owned by **Users** domain; Admin can read and modify via Users service)
- Subscription plan definitions and entitlement enforcement (owned by **Subscriptions** domain; Admin can override via Subscriptions service)
- Business documents: deals, proposals, contracts, invoices (owned by respective domains; Admin has read-only access)
- Application infrastructure monitoring (DevOps concern; outside SoloDesk application scope)

## Core Concepts

**Admin User** — A User with `role: admin`. Admins have access to the Admin module and all cross-domain read operations. Admin role is set on the User record.

**Audit Log Entry** — An immutable system-wide record of significant events: `event_type`, `actor_user_id`, `target_type`, `target_id`, `description`, `ip_address`, `timestamp`. Never deleted. Used for compliance, support, and security review.

**System Template** — A reusable proposal or contract template created by Admins and made available to all users or specific plan tiers. Contains `template_type` (`proposal` | `contract`), `name`, `content`, `plan_tier_required`, `is_active`.

**Feature Flag** — A named boolean or percentage rollout configuration: `flag_name`, `is_enabled`, `rollout_percentage`, `target_user_ids[]`. Controls gradual feature releases.

**AI Cost Record** — A per-request log of AI generation costs: `user_id`, `ai_module`, `model_used`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `timestamp`. Aggregated for cost monitoring dashboards.

**Platform Metric** — A periodic snapshot of platform health: registered user count, active subscription count, deals created, proposals generated, AI calls made, error rates.

## Business Rules

- There must always be at least one active Admin user. The system blocks deletion or suspension of the last remaining Admin account.
- Admin actions are always recorded in the Audit Log. Audit log entries cannot be modified or deleted.
- Admins can read any user's data for support purposes. They must not modify business records (deals, proposals, contracts) unless via an explicit break-glass action that is double-logged.
- System Templates are versioned. Activating a new version does not alter documents already generated from a previous version.
- Feature flags take immediate effect without a deployment. Flag changes are audit-logged with the admin who changed them.
- AI Cost monitoring is read-only at the Admin level; Admins can view but cannot alter AI generation parameters directly (those are owned by the **AI** domain).
- Subscription overrides (e.g. granting a free trial of Pro plan) expire at a configured date unless renewed.

## Lifecycle

Admin domain objects (Audit Log Entries, AI Cost Records) are append-only and have no lifecycle state transitions. System Templates have a simple status:

```
[Template Created: draft]
        │
  Admin reviews and activates
        │
        ▼
    [active]  ──── Admin deactivates ────► [inactive]
                                                │
                                         (new version
                                          created as draft)
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Users** | Admin reads and modifies user records (status, role) via Users service. |
| **Subscriptions** | Admin can manually override subscription status and plan via Subscriptions service. |
| **Auth** | Admin can force-revoke sessions via Auth service. |
| **Deals / Clients / Proposals / Contracts / Invoices** | Admin has read-only access for support purposes. |
| **Analytics** | Admin views platform-wide aggregated analytics (not per-user). |
| **AI** | Admin monitors AI cost records and can view AI usage patterns. |
| **All Domains** | All domains write to the shared Audit Log which Admin reads. |

## Events

Admin primarily **consumes** events from other domains to populate the Audit Log. It may also produce:

| Event | Trigger | Consumers |
|---|---|---|
| `admin.user_suspended_by_admin` | Admin suspends a user | Auth (revoke sessions), Reminders (cancel pending) |
| `admin.subscription_overridden` | Admin manually changes a plan | Subscriptions, Auth (re-issue token) |
| `admin.feature_flag_changed` | Admin toggles a feature flag | All modules (flag evaluation cache invalidated) |
| `admin.template_activated` | New system template published | Users (notification of new template available) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Admin** | Full access to Admin module: user management, audit logs, template CRUD, feature flags, AI cost monitoring, subscription overrides, platform metrics |
| **Authenticated User** | None (Admin module is inaccessible to regular users) |
| **Anonymous** | None |

## Future Considerations

- Role-based Admin sub-roles: `super_admin` vs. `support_agent` with restricted permissions
- Self-service admin dashboard for SaaS metrics (MRR, churn, LTV)
- Automated anomaly alerts: flag unusual AI usage spikes or login patterns
- Data export for GDPR compliance (full user data export on request)
- Right-to-erasure workflow: coordinated hard-delete across all domains on verified user request
- Multi-tenant admin: if SoloDesk expands to agency accounts, per-agency admin roles
