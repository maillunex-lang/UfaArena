"""Account access recovery: hashed one-time recovery code on users (no SMTP on the server). Additive.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("recovery_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "recovery_hash")
