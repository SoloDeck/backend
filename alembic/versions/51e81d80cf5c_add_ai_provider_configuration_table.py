"""add ai provider configuration table

Revision ID: 51e81d80cf5c
Revises: u8b9c0d1e2f3
Create Date: 2026-07-31 21:19:40.289795
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '51e81d80cf5c'
down_revision: str | None = 'u8b9c0d1e2f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'ai_provider_configuration',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('llm_provider', sa.String(length=20), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.execute("""
        INSERT INTO ai_provider_configuration (
            id,
            llm_provider,
            updated_at,
            updated_by
        )
        VALUES (
            gen_random_uuid(),
            'groq',
            NOW(),
            NULL
        )
    """)


def downgrade() -> None:
    op.drop_table('ai_provider_configuration')