"""Caravan location and travel (lore stage S4). Additive; modules reuse fortress_buildings.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_caravans",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("location", sa.String(32), nullable=False),
        sa.Column("destination", sa.String(32), nullable=True),
        sa.Column("depart_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrive_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trips", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("player_caravans")
