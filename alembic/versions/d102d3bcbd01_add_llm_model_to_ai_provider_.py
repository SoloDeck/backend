"""add llm model to ai provider configuration

Revision ID: d102d3bcbd01
Revises: v9c0d1e2f3a4
Create Date: ...
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d102d3bcbd01"
down_revision: str | None = "v9c0d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_configuration",
        sa.Column(
            "llm_model",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE ai_provider_configuration
        SET llm_model = 'llama-3.3-70b-versatile'
        WHERE llm_provider = 'groq'
          AND llm_model IS NULL
        """
    )

    op.alter_column(
        "ai_provider_configuration",
        "llm_model",
        existing_type=sa.String(length=100),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column(
        "ai_provider_configuration",
        "llm_model",
    )