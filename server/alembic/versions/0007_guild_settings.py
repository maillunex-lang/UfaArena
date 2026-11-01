"""Guild settings JSON (required power, auto-accept, chat notifications). Additive.

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guilds", sa.Column("settings", sa.JSON(), server_default="{}", nullable=False))


def downgrade() -> None:
    op.drop_column("guilds", "settings")
