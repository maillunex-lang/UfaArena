"""AI participation switches: player_profiles.ai_prefs, guilds.ai_policy (additive).

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("player_profiles", sa.Column("ai_prefs", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("guilds", sa.Column("ai_policy", sa.JSON(), server_default="{}", nullable=False))


def downgrade() -> None:
    op.drop_column("guilds", "ai_policy")
    op.drop_column("player_profiles", "ai_prefs")
