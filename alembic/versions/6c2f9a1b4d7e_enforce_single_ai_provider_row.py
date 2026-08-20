"""enforce single ai_provider_configuration row

`ai_provider_configuration` is meant to hold exactly one row for the whole
platform, but nothing enforced that — the rule lived only in a comment on the
model. The seed INSERT uses gen_random_uuid(), so re-running it adds a second
row instead of colliding, and the repository reads the table with a bare
`select(...)` (no LIMIT, no ORDER BY). Because ProviderFactory re-reads this row
on every AI request, a duplicate makes the platform-wide LLM provider
nondeterministic per query rather than failing visibly.

This adds a boolean `is_singleton` that is always TRUE (CHECK) and UNIQUE, so
Postgres rejects a second row outright.

If the upgrade aborts complaining about duplicates, the table already has more
than one row. Nothing is deleted automatically — inspect and pick the one to
keep, e.g.:

    SELECT id, llm_provider, updated_at FROM ai_provider_configuration
    ORDER BY updated_at DESC;
    DELETE FROM ai_provider_configuration WHERE id <> '<id-to-keep>';

Revision ID: 6c2f9a1b4d7e
Revises: 51e81d80cf5c
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '6c2f9a1b4d7e'
down_revision: str | None = '51e81d80cf5c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail with an actionable message rather than a raw unique-violation.
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM ai_provider_configuration"))
    if count is not None and count > 1:
        raise RuntimeError(
            f"ai_provider_configuration has {count} rows but must have exactly 1. "
            "Delete the extras before running this migration — see the module "
            "docstring for the queries."
        )

    op.add_column(
        'ai_provider_configuration',
        sa.Column(
            'is_singleton',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
    )
    op.create_check_constraint(
        'ck_ai_provider_singleton',
        'ai_provider_configuration',
        'is_singleton IS TRUE',
    )
    op.create_unique_constraint(
        'uq_ai_provider_singleton',
        'ai_provider_configuration',
        ['is_singleton'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_ai_provider_singleton', 'ai_provider_configuration', type_='unique')
    op.drop_constraint('ck_ai_provider_singleton', 'ai_provider_configuration', type_='check')
    op.drop_column('ai_provider_configuration', 'is_singleton')
