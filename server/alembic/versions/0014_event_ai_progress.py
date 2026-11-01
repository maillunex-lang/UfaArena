"""Living World AI, phase 5: world events get a separate "AI residents' contribution" counter (decision D-05).

Revision ID: 0014
Revises: 0013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("world_events") as b:
        b.add_column(sa.Column("ai_progress", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("world_events") as b:
        b.drop_column("ai_progress")
