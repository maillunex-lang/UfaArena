"""Player gender from the hero creation window: m | f | NULL (not asked yet). Used to choose who flirts with an adult
player in private messages (a woman writes to a man, a confident "macho" to a woman). Additive, nothing is lost.

Revision ID: 0016
Revises: 0015
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_profiles") as b:
        b.add_column(sa.Column("gender", sa.String(1), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("player_profiles") as b:
        b.drop_column("gender")
