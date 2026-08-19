"""add sessions_revoked_at to users

Admin suspend/revoke-sessions actions had no way to invalidate a user's already-issued
access token — get_current_user only checked JWT signature/expiry, so a suspended or
"session-revoked" user kept full API access for up to 15 minutes (the access token TTL)
after the admin action. A single per-user cutoff timestamp, checked against each token's
own `iat` claim, closes this without needing to track every issued access token: any
token minted before the cutoff is rejected, regardless of its own expiry.

Revision ID: v3736329f982
Revises: u8b9c0d1e2f3
Create Date: 2026-08-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'v3736329f982'
down_revision: str | None = 'u8b9c0d1e2f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('sessions_revoked_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'sessions_revoked_at')
