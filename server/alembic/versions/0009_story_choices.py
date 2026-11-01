"""Story choices and story flags (lore stage S2: decisions with consequences). Additive.

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "story_choices",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("choice_id", sa.String(64), primary_key=True),
        sa.Column("option", sa.String(32), nullable=False),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "player_story_flags",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("flag", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("player_story_flags")
    op.drop_table("story_choices")
