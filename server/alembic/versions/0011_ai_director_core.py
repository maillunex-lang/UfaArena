"""Living World AI, phase 2 (director core): task queue + history, game event queue, schedule profiles,
persona schedule profile and session. Additive.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ai_tasks",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(128), nullable=False, unique=True),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("persona_id", sa.String(36), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("run_after", TS, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", TS, nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
    )
    op.create_index("ix_ai_tasks_kind", "ai_tasks", ["kind"])
    op.create_index("ix_ai_tasks_persona_id", "ai_tasks", ["persona_id"])
    op.create_index("ix_ai_tasks_status", "ai_tasks", ["status"])
    op.create_index("ix_ai_tasks_run_after", "ai_tasks", ["run_after"])
    op.create_table(
        "ai_task_history",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("task_id", BIG, nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("persona_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
    )
    op.create_index("ix_ai_task_history_task_id", "ai_task_history", ["task_id"])
    op.create_index("ix_ai_task_history_persona_id", "ai_task_history", ["persona_id"])
    op.create_table(
        "ai_events",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("persona_user_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("due_at", TS, nullable=False),
        sa.Column("handled_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_ai_events_kind", "ai_events", ["kind"])
    op.create_index("ix_ai_events_due_at", "ai_events", ["due_at"])
    op.create_index("ix_ai_events_handled_at", "ai_events", ["handled_at"])
    op.create_table(
        "ai_schedule_profiles",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("hours", sa.JSON(), nullable=False),
        sa.Column("peak_hours", sa.JSON(), nullable=False),
        sa.Column("tz_shift", sa.Integer(), nullable=False),
        sa.Column("session_minutes", sa.Integer(), nullable=False),
        sa.Column("rest_weekdays", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
    )
    op.add_column("ai_personas", sa.Column("schedule_profile", sa.String(32), nullable=True))
    op.add_column("ai_personas", sa.Column("session_until", TS, nullable=True))


def downgrade() -> None:
    op.drop_column("ai_personas", "session_until")
    op.drop_column("ai_personas", "schedule_profile")
    op.drop_table("ai_schedule_profiles")
    op.drop_index("ix_ai_events_handled_at", "ai_events")
    op.drop_index("ix_ai_events_due_at", "ai_events")
    op.drop_index("ix_ai_events_kind", "ai_events")
    op.drop_table("ai_events")
    op.drop_index("ix_ai_task_history_persona_id", "ai_task_history")
    op.drop_index("ix_ai_task_history_task_id", "ai_task_history")
    op.drop_table("ai_task_history")
    op.drop_index("ix_ai_tasks_run_after", "ai_tasks")
    op.drop_index("ix_ai_tasks_status", "ai_tasks")
    op.drop_index("ix_ai_tasks_persona_id", "ai_tasks")
    op.drop_index("ix_ai_tasks_kind", "ai_tasks")
    op.drop_table("ai_tasks")
