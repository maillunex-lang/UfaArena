"""Player age group for adult AI content (Living Community decision D-C1): adult | minor | NULL (not asked yet).
Additive; existing players stay NULL and are treated as not adult until they answer.

Revision ID: 0015
Revises: 0014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("player_profiles") as b:
        b.add_column(sa.Column("age_group", sa.String(8), nullable=True))
        b.add_column(sa.Column("age_set_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("player_profiles") as b:
        b.drop_column("age_set_at")
        b.drop_column("age_group")
