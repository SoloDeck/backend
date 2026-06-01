# User Aggregate

## Aggregate Root

**`User`** — the central identity record for a SoloDesk account.

Every user-scoped table in the system filters by `owner_user_id = User.id`. User is the only true leaf domain: nothing it owns depends on another business domain.

## Child Entities

| Entity | Relation | Notes |
|--------|----------|-------|
| `ProfessionalProfile` | Embedded value object (same row) | Skills, rate, portfolio |
| `Preferences` | Embedded value object (same row) | Locale, timezone, theme |

No child entities live in separate tables owned by the Users domain. Auth credentials, OAuth identities, and subscriptions are owned by their respective domains.

## Value Objects

| Value Object | Fields | Invariants |
|-------------|--------|-----------|
| `ProfessionalProfile` | `skills[]`, `specialization`, `default_hourly_rate`, `currency`, `portfolio_url`, `business_name` | `currency` must be a valid ISO 4217 code; `default_hourly_rate` ≥ 0 |
| `Preferences` | `locale`, `timezone`, `notification_channel`, `theme` | `timezone` must be a valid IANA tz string |

## Invariants

1. `email` is globally unique and immutable once set (changing email requires re-verification — not yet implemented).
2. `role` may only be `freelancer` or `admin`. Promotion to `admin` is only permitted by an existing `admin`.
3. `status` transitions: `active → suspended → active` (reversible), `active → deleted` (terminal via soft-delete).
4. A deleted user (`deleted_at IS NOT NULL`) must not appear in any user-facing queries.
5. `hashed_password` is `NULL` for OAuth-only accounts. Such users cannot use credential login.

## Lifecycle

```
[Registration / OAuth]
        │
        ▼
     active
        │
   (admin action)
        ▼
   suspended  ←──── active
        │
   (re-activation)
        ▼
     active
        │
   (self-delete or admin delete)
        ▼
     deleted  (soft — deleted_at set)
```

## Commands

| Command | Actor | Preconditions |
|---------|-------|--------------|
| `RegisterUser` | Anonymous | Email not already taken |
| `UpdateProfile` | Self | User is `active` |
| `UpdateProfessionalProfile` | Self | User is `active` |
| `UpdatePreferences` | Self | User is `active` |
| `SuspendUser` | Admin | User is `active` |
| `ReactivateUser` | Admin | User is `suspended` |
| `DeleteUser` | Self / Admin | User is `active` or `suspended` |

## Events

| Event | Payload | Consumers |
|-------|---------|-----------|
| `users.user_created` | `user_id`, `email`, `role` | Subscriptions (create Free plan) |
| `users.user_deleted` | `user_id` | All domains (cancel reminders, anonymize records) |
| `users.status_changed` | `user_id`, `old_status`, `new_status` | Auth (invalidate tokens on suspend) |

## Persistence Considerations

- All columns are on a single `users` table (no child tables in this domain).
- Soft delete via `deleted_at TIMESTAMPTZ` — every query must add `WHERE deleted_at IS NULL`.
- `updated_at` is maintained by a PostgreSQL trigger (`set_updated_at()`), not the ORM.
- `hashed_password` is nullable; bcrypt hash stored when set.

## Future Scaling Considerations

- If user profile data grows (portfolio attachments, certifications), consider a separate `user_profiles` table.
- Email change flow will require a verification token domain (currently not modeled).
- For GDPR right-to-erasure, soft-delete is insufficient — a data anonymization job will be needed.
