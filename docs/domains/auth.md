# Auth Domain

## Purpose

Provide secure identity verification and session management for all users of SoloDesk. This domain is the entry point for every user interaction and acts as the gatekeeper for all protected resources.

## Responsibilities

- Credential-based login (email + password)
- Google OAuth 2.0 login and callback handling
- JWT access token issuance and validation
- Refresh token lifecycle (issue, rotate, revoke)
- Logout and session termination
- Password reset flow (request, validate token, apply new password)
- Token blacklisting on logout or suspicious activity

## Does Not Own

- User profile data (owned by **Users** domain)
- Role and permission definitions beyond token claims (owned by **Users** domain)
- Subscription entitlement checks (owned by **Subscriptions** domain)
- Audit logging of business actions (owned by **Admin** domain)

## Core Concepts

**Credential** — An email + hashed password pair associated with a User account.

**Access Token** — A short-lived JWT (e.g. 15 minutes) that encodes `user_id`, `email`, `role`, and `subscription_tier`. Passed in `Authorization: Bearer` header.

**Refresh Token** — A long-lived opaque token (e.g. 30 days) stored server-side and used to obtain a new Access Token without re-authentication.

**OAuth Identity** — An external identity record linking a Google `sub` claim to a SoloDesk `user_id`. One user may have both credential and OAuth identities.

**Session** — The logical period from login to logout or token expiry.

## Business Rules

- A user may not hold more than one active refresh token per device/client unless multi-device login is explicitly enabled.
- Refresh token rotation: every refresh call invalidates the old token and issues a new one.
- On logout, the current access token is blacklisted until its natural expiry.
- Failed login attempts must be rate-limited (configurable threshold, e.g. 5 attempts / 15 min).
- Password reset tokens expire after 1 hour and are single-use.
- OAuth login creates a new User record on first login if none exists; subsequent logins reuse the existing record.
- JWT claims must include `subscription_tier` so downstream services can enforce entitlement without additional DB calls on every request.

## Lifecycle

```
[Not Authenticated]
      │
      ├─ POST /auth/login (credentials) ──────────────────────┐
      ├─ GET  /auth/google/callback (OAuth code exchange) ──┐  │
      │                                                     ▼  ▼
      │                                          [Access Token + Refresh Token Issued]
      │                                                     │
      │                              ┌──────────────────────┤
      │                              │                      │
      │                    [Token Valid]           [Token Expired]
      │                              │                      │
      │                         [Authorized]        POST /auth/refresh
      │                              │                      │
      │                              │               [New Access Token]
      │                              │
      │                    POST /auth/logout
      │                              │
      └──────────────────────────────┘
                           [Token Blacklisted]
```

## Relationships

| Related Domain | Nature |
|---|---|
| **Users** | Auth reads User credentials and profile to populate JWT claims; on OAuth first login, Auth instructs Users to create a new record. |
| **Subscriptions** | Auth embeds `subscription_tier` in the JWT, sourced from Subscriptions at login time. |
| **Admin** | Admin may force-revoke sessions for flagged users. |

## Events

| Event | Trigger | Consumers |
|---|---|---|
| `auth.user_logged_in` | Successful login | Analytics (session tracking), Admin (audit) |
| `auth.user_logged_out` | Explicit logout | Token blacklist service |
| `auth.token_refreshed` | Successful refresh | Audit log |
| `auth.login_failed` | Bad credentials | Rate limiter, Admin (security alerts) |
| `auth.password_reset_requested` | Reset request submitted | Email/notification worker |
| `auth.password_reset_completed` | Password successfully changed | Auth (invalidate all refresh tokens) |

## Permissions

| Actor | Allowed Actions |
|---|---|
| **Anonymous** | Login, Google OAuth, request password reset |
| **Authenticated User** | Logout, refresh token, change own password |
| **Admin** | Revoke any user's sessions, view login audit logs |

## Future Considerations

- Multi-factor authentication (TOTP / SMS OTP)
- Per-device session management UI
- Suspicious login detection (geo-anomaly, new device alerts)
- SSO / SAML support for agency/team accounts
- Short-lived magic link login for low-friction onboarding
