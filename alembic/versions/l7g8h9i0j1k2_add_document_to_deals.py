"""add document_url and document_filename to deals

Revision ID: l7g8h9i0j1k2
Revises: d8afe394da6d
Create Date: 2026-07-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l7g8h9i0j1k2"
down_revision: str | None = "d8afe394da6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("document_url", sa.String(2048), nullable=True))
    op.add_column("deals", sa.Column("document_filename", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "document_filename")
    op.drop_column("deals", "document_url")
