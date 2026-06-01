# Users Domain

## Purpose

Maintain the canonical record of every SoloDesk user — their identity, professional profile, and personal preferences. The Users domain is the single source of truth for who a person is within the system, while Auth handles how they prove that identity.

## Responsibilities

- Create and store user accounts (on registration or first OAuth login)
- Manage user profile: full name, avatar, bio, contact info
- Manage professional profile: skills, freelance specialization, hourly rate, portfolio link
- Store and serve user preferences (locale, timezone, notification settings, UI theme)
- Provide user lookup by ID and email for internal domain use
- Soft-delete user accounts (retain data for compliance; mark as inactive)
- Email change flow (verify new email before committing)

## Does Not Own

- Authentication credentials or sessions (owned by **Auth** domain)
- Subscription tier or billing entitlements (owned by **Subscriptions** domain)
- Client or deal records created by the user (owned by **Clients** and **Deals** domains)
- Admin-level user management actions such as banning (owned by **Admin** domain)

## Core Concepts

**User** — The root aggregate. Represents a SoloDesk freelancer account. Has a unique `user_id` (UUID), `email`, `full_name`, `role` (`freelancer` | `admin`), and `status` (`active` | `suspended` | `deleted`).

**Professional Profile** — A nested value object on User. Stores freelance-specific information: `skills[]`, `specialization`, `default_hourly_rate`, `currency`, `portfolio_url`, `business_name`.

**Preferences** — A nested value object on User. Stores `locale` (e.g. `vi`, `en`), `timezone`, `notification_channel` (`email` | `in_app` | `both`), `theme` (`light` | `dark`).

**Avatar** — A URL reference to the user's uploaded profile image, stored in object storage.

## Business Rules

- `email` must be unique across all users. Email changes require verification of the new address before the old one is replaced.
- `role` is set at account creation and can only be changed by an Admin.
- A user in `suspended` status can authenticate but receives a `403` on all business operations.
- A user in `deleted` status cannot authenticate. Their records remain in the database with a `deleted_at` timestamp.
- `default_hourly_rate` is informational; it does not automatically populate Deals or Proposals (user must explicitly choose to pre-fill).
- `locale` and `timezone` affect all date/time rendering and reminder scheduling for the user.
- A user must have a completed Professional Profile before they can generate AI-assisted Proposals or Contracts.

## Lifecycle

```
[Registration / OAuth First Login]
         │
         ▼
    [Status: active]
         │
         ├─ User updates profile → [Profile updated]
         ├─ Admin suspends user  → [Status: suspended]
         │                               │
         │                         Admin reinstates
         │                               │
         │                         [Status: active]
         │
         └─ User requests deletion → [Status: deleted, deleted_at set]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Auth** | Auth reads User to validate credentials and populate JWT claims. Auth notifies Users to create a record on first OAuth login. |
| **Subscriptions** | Subscriptions references `user_id`; Users does not store subscription data directly. |
| **Clients** | Each Client record is owned by a User (`owner_user_id`). |
| **Deals** | Each Deal is owned by a User. |
| **Reminders** | Reminders are scoped to a User's context. |
| **Analytics** | Analytics aggregates data per User. |
| **Admin** | Admin reads User records for management; can change `role` and `status`. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `users.user_created` | New account registered | Subscriptions (create free plan), Admin (audit), Analytics |
| `users.profile_updated` | Profile fields changed | AI (re-index user context for generation) |
| `users.user_suspended` | Admin suspends account | Auth (invalidate active sessions) |
| `users.user_deleted` | Soft delete applied | Auth (revoke all tokens), Reminders (cancel pending) |
| `users.email_changed` | New email verified | Auth (update credential record) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Authenticated User** | Read and update own profile, update own preferences, request own account deletion |
| **Admin** | Read any user profile, change role, suspend/reinstate/delete any user |
| **Anonymous** | None |

## Future Considerations

- Team accounts: one billing owner with multiple team members sharing a workspace
- Profile visibility settings for a future public freelancer directory
- Integration with LinkedIn for profile import
- Identity verification (KYC) for high-value contract signing
- Reputation/rating system from client feedback
