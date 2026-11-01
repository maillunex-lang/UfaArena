"""Living World AI, phase 3 (personalities, tiers, speech, memory): persona traits/ambitions/habits/voice/counters/
mood/tier/pace/version, memory kind/importance/created_at, archetypes, snapshots, memory archive, biographies.
Additive; existing personas are filled lazily by the Director (no progress is changed).

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)

PERSONA_COLS = [
    ("traits", sa.JSON(), "{}"), ("ambitions", sa.JSON(), "[]"), ("habits", sa.JSON(), "[]"), ("voice", sa.JSON(), "{}"),
    ("counters", sa.JSON(), "{}"), ("mood", sa.Float(), "0"), ("pace", sa.Float(), "1"),
    ("personality_version", sa.Integer(), "0"),
]


def upgrade() -> None:
    with op.batch_alter_table("ai_personas") as b:
        for name, typ, default in PERSONA_COLS:
            b.add_column(sa.Column(name, typ, nullable=False, server_default=default))
        b.add_column(sa.Column("tier", sa.String(16), nullable=True))
    op.create_index("ix_ai_personas_tier", "ai_personas", ["tier"])
    with op.batch_alter_table("ai_memory") as b:
        b.add_column(sa.Column("kind", sa.String(24), nullable=False, server_default="fact"))
        b.add_column(sa.Column("importance", sa.Float(), nullable=False, server_default="1"))
        b.add_column(sa.Column("created_at", TS, nullable=True))
    op.create_index("ix_ai_memory_kind", "ai_memory", ["kind"])
    op.create_index("ix_ai_memory_created_at", "ai_memory", ["created_at"])

    op.create_table(
        "ai_archetypes",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("styles", sa.JSON(), nullable=False),
        sa.Column("trait_bias", sa.JSON(), nullable=False),
        sa.Column("ambitions", sa.JSON(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "ai_persona_snapshots",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("persona_id", sa.String(36), sa.ForeignKey("ai_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_ai_persona_snapshots_persona_id", "ai_persona_snapshots", ["persona_id"])
    op.create_table(
        "ai_memory_archive",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("persona_id", sa.String(36), sa.ForeignKey("ai_personas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("persona_id", "period", name="uq_ai_memory_archive_period"),
    )
    op.create_index("ix_ai_memory_archive_persona_id", "ai_memory_archive", ["persona_id"])
    op.create_table(
        "ai_biographies",
        sa.Column("persona_id", sa.String(36), sa.ForeignKey("ai_personas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_biographies")
    op.drop_index("ix_ai_memory_archive_persona_id", table_name="ai_memory_archive")
    op.drop_table("ai_memory_archive")
    op.drop_index("ix_ai_persona_snapshots_persona_id", table_name="ai_persona_snapshots")
    op.drop_table("ai_persona_snapshots")
    op.drop_table("ai_archetypes")
    op.drop_index("ix_ai_memory_created_at", table_name="ai_memory")
    op.drop_index("ix_ai_memory_kind", table_name="ai_memory")
    with op.batch_alter_table("ai_memory") as b:
        b.drop_column("created_at")
        b.drop_column("importance")
        b.drop_column("kind")
    op.drop_index("ix_ai_personas_tier", table_name="ai_personas")
    with op.batch_alter_table("ai_personas") as b:
        b.drop_column("tier")
        for name, _, _ in reversed(PERSONA_COLS):
            b.drop_column(name)
