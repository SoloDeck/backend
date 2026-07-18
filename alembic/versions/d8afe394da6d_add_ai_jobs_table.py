"""add ai_jobs table

Revision ID: d8afe394da6d
Revises: f85cb132e701
Create Date: 2026-07-03 19:39:17.132877
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8afe394da6d"
down_revision: str | None = "f85cb132e701"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- ENUM types (ORM declares them with create_type=False) ----------------
    op.execute(
        "CREATE TYPE ai_job_status AS ENUM "
        "('queued', 'running', 'succeeded', 'failed', 'cancelled')"
    )
    op.execute("CREATE TYPE ai_job_entity_type AS ENUM ('deal', 'proposal', 'contract')")

    # --- ai_jobs (polymorphic — no FK on entity_id) ----------------------------
    op.create_table(
        "ai_jobs",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "lead_qualifier",
                "proposal_generator",
                "contract_generator",
                "followup_generator",
                name="ai_module_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            postgresql.ENUM(
                "deal", "proposal", "contract", name="ai_job_entity_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                name="ai_job_status",
                create_type=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_jobs_entity", "ai_jobs", ["entity_type", "entity_id"], unique=False)
    op.create_index("idx_ai_jobs_owner", "ai_jobs", ["owner_user_id"], unique=False)
    op.create_index(
        "uq_ai_jobs_owner_idempotency_key",
        "ai_jobs",
        ["owner_user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_jobs_owner_idempotency_key",
        table_name="ai_jobs",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index("idx_ai_jobs_owner", table_name="ai_jobs")
    op.drop_index("idx_ai_jobs_entity", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.execute("DROP TYPE ai_job_entity_type")
    op.execute("DROP TYPE ai_job_status")
