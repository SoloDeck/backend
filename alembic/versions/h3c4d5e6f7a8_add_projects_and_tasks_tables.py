"""add projects and tasks tables

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7
Create Date: 2026-06-28 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'h3c4d5e6f7a8'
down_revision: str | None = 'g2b3c4d5e6f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _exec(sql: str) -> None:
    op.execute(sql)


def upgrade() -> None:
    # --- ENUM types (ORM declares them with create_type=False) ----------------
    _exec("CREATE TYPE project_status AS ENUM ('planning', 'active', 'on_hold', 'completed')")
    _exec("CREATE TYPE task_status AS ENUM ('todo', 'in_progress', 'review', 'done')")
    _exec("CREATE TYPE task_priority AS ENUM ('low', 'medium', 'high')")
    _exec("CREATE TYPE task_entity_type AS ENUM ('project', 'deal', 'reminder')")

    # --- projects -------------------------------------------------------------
    op.create_table(
        'projects',
        sa.Column('deal_id', sa.UUID(), nullable=True),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM(
                'planning', 'active', 'on_hold', 'completed',
                name='project_status', create_type=False,
            ),
            server_default='planning',
            nullable=False,
        ),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_projects_owner', 'projects', ['owner_id'], unique=False)
    op.create_index('idx_projects_owner_status', 'projects', ['owner_id', 'status'], unique=False)
    op.create_index('idx_projects_deal', 'projects', ['deal_id'], unique=False)

    # --- tasks (polymorphic — no FK on entity_id) -----------------------------
    op.create_table(
        'tasks',
        sa.Column(
            'entity_type',
            postgresql.ENUM(
                'project', 'deal', 'reminder',
                name='task_entity_type', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'priority',
            postgresql.ENUM('low', 'medium', 'high', name='task_priority', create_type=False),
            server_default='medium',
            nullable=False,
        ),
        sa.Column(
            'status',
            postgresql.ENUM(
                'todo', 'in_progress', 'review', 'done',
                name='task_status', create_type=False,
            ),
            server_default='todo',
            nullable=False,
        ),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tasks_entity', 'tasks', ['entity_type', 'entity_id'], unique=False)
    op.create_index(
        'idx_tasks_entity_status', 'tasks', ['entity_type', 'entity_id', 'status'], unique=False
    )

    # --- checklist_items ------------------------------------------------------
    op.create_table(
        'checklist_items',
        sa.Column('task_id', sa.UUID(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('is_done', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_checklist_items_task', 'checklist_items', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_checklist_items_task', table_name='checklist_items')
    op.drop_table('checklist_items')
    op.drop_index('idx_tasks_entity_status', table_name='tasks')
    op.drop_index('idx_tasks_entity', table_name='tasks')
    op.drop_table('tasks')
    op.drop_index('idx_projects_deal', table_name='projects')
    op.drop_index('idx_projects_owner_status', table_name='projects')
    op.drop_index('idx_projects_owner', table_name='projects')
    op.drop_table('projects')
    _exec("DROP TYPE task_entity_type")
    _exec("DROP TYPE task_priority")
    _exec("DROP TYPE task_status")
    _exec("DROP TYPE project_status")
