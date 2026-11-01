"""Living World AI, phase 4 (social system, chats, guilds, real players): relationships, informal groups and members,
AI guild state, player watch for outreach limits, guild alliances with members and proposals (D-12). Additive.

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ai_relationships",
        sa.Column("id", BIG, primary_key=True, autoincrement=True),
        sa.Column("subject_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sympathy", sa.Float(), nullable=False),
        sa.Column("trust", sa.Float(), nullable=False),
        sa.Column("rivalry", sa.Float(), nullable=False),
        sa.Column("dislike", sa.Float(), nullable=False),
        sa.Column("interactions", sa.Integer(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("last_at", TS, nullable=False),
        sa.UniqueConstraint("subject_id", "object_id", name="uq_ai_relationship_pair"),
    )
    op.create_index("ix_ai_relationships_subject_id", "ai_relationships", ["subject_id"])
    op.create_index("ix_ai_relationships_object_id", "ai_relationships", ["object_id"])
    op.create_table(
        "ai_social_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("founder_id", sa.String(36), nullable=True),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "ai_social_group_members",
        sa.Column("group_id", sa.String(36), sa.ForeignKey("ai_social_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("joined_at", TS, nullable=False),
    )
    op.create_index("ix_ai_social_group_members_user_id", "ai_social_group_members", ["user_id"])
    op.create_table(
        "ai_guild_state",
        sa.Column("guild_id", sa.String(36), sa.ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reputation", sa.Float(), nullable=False),
        sa.Column("traditions", sa.JSON(), nullable=False),
        sa.Column("relations", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("next_election_at", TS, nullable=True),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_table(
        "ai_player_watch",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("seen_at", TS, nullable=True),
        sa.Column("contacted_at", TS, nullable=True),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("contacts_today", sa.Integer(), nullable=False),
        sa.Column("week", sa.String(10), nullable=False),
        sa.Column("invites_week", sa.Integer(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False),
    )
    op.create_table(
        "guild_alliances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("founder_guild_id", sa.String(36), nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "guild_alliance_members",
        sa.Column("guild_id", sa.String(36), sa.ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("alliance_id", sa.String(36), sa.ForeignKey("guild_alliances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", TS, nullable=False),
    )
    op.create_index("ix_guild_alliance_members_alliance_id", "guild_alliance_members", ["alliance_id"])
    op.create_table(
        "guild_alliance_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_guild_id", sa.String(36), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_guild_id", sa.String(36), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("proposed_by", sa.String(36), nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_guild_alliance_proposals_from_guild_id", "guild_alliance_proposals", ["from_guild_id"])
    op.create_index("ix_guild_alliance_proposals_to_guild_id", "guild_alliance_proposals", ["to_guild_id"])


def downgrade() -> None:
    op.drop_index("ix_guild_alliance_proposals_to_guild_id", table_name="guild_alliance_proposals")
    op.drop_index("ix_guild_alliance_proposals_from_guild_id", table_name="guild_alliance_proposals")
    op.drop_table("guild_alliance_proposals")
    op.drop_index("ix_guild_alliance_members_alliance_id", table_name="guild_alliance_members")
    op.drop_table("guild_alliance_members")
    op.drop_table("guild_alliances")
    op.drop_table("ai_player_watch")
    op.drop_table("ai_guild_state")
    op.drop_index("ix_ai_social_group_members_user_id", table_name="ai_social_group_members")
    op.drop_table("ai_social_group_members")
    op.drop_table("ai_social_groups")
    op.drop_index("ix_ai_relationships_object_id", table_name="ai_relationships")
    op.drop_index("ix_ai_relationships_subject_id", table_name="ai_relationships")
    op.drop_table("ai_relationships")
