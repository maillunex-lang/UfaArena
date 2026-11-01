"""Database schema for URALIA (DATABASE_API_BLUEPRINT.md).

PostgreSQL is the source of truth. Wallet balances are a cache of the immutable
`wallet_transactions` ledger and are always updated in the same DB transaction.
Tables for guilds / AI population / admin are defined now so the schema is
stable, but their gameplay endpoints belong to later functional blocks.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base, utcnow


def _uuid() -> str:
    return str(uuid.uuid4())


TS = DateTime(timezone=True)


# ---------------------------------------------------------------- accounts
class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), default="guest")  # guest | linked
    device_id: Mapped[str | None] = mapped_column(String(128), index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    recovery_hash: Mapped[str | None] = mapped_column(String(255))  # scrypt of the one-time recovery code
    external_provider: Mapped[str | None] = mapped_column(String(32))
    external_subject: Mapped[str | None] = mapped_column(String(255))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    profile: Mapped[PlayerProfile] = relationship(back_populates="user", uselist=False)


class PlayerProfile(Base):
    __tablename__ = "player_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    uralia_id: Mapped[str] = mapped_column(String(16), unique=True)  # public short id
    nickname: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=1)
    exp: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)  # AI personas are always flagged
    vip_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # cosmetic/convenience only
    vip_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cosmetics: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # equipped cosmetics
    hero_shards: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # shards of not-yet-owned heroes
    afk_last_claim_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    summon_pity: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    # social
    avatar: Mapped[str] = mapped_column(String(32), default="", server_default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(TS, index=True)
    presence_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    reputation: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    power: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # cached top-5 power for search/matchmaking
    ai_prefs: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # player's AI-participation switches
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class SessionToken(Base):
    """Refresh-token session. Only the SHA-256 of the token is stored; tokens rotate."""

    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TS)
    rotated_at: Mapped[datetime | None] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    user_agent: Mapped[str | None] = mapped_column(String(255))


# ---------------------------------------------------------------- static game data
class Faction(Base):
    __tablename__ = "factions"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    is_rare: Mapped[bool] = mapped_column(Boolean, default=False)
    strong_against: Mapped[str | None] = mapped_column(String(32))
    emblem: Mapped[str] = mapped_column(String(32), default="", server_default="")
    color: Mapped[str] = mapped_column(String(16), default="#ffffff", server_default="#ffffff")
    accent: Mapped[str] = mapped_column(String(16), default="#ffffff", server_default="#ffffff")
    playable: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class HeroClass(Base):
    __tablename__ = "classes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))  # tank | damage | support | control


class Hero(Base):
    __tablename__ = "heroes"
    code: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128), default="")
    faction_code: Mapped[str] = mapped_column(ForeignKey("factions.code"))
    class_code: Mapped[str] = mapped_column(ForeignKey("classes.code"))
    rarity: Mapped[int] = mapped_column(Integer)  # 1..6
    base_hp: Mapped[int] = mapped_column(Integer)
    base_atk: Mapped[int] = mapped_column(Integer)
    base_def: Mapped[int] = mapped_column(Integer)
    base_spd: Mapped[int] = mapped_column(Integer)
    skill: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(64))  # client visual id (content package)
    lore: Mapped[str] = mapped_column(Text, default="")
    is_enemy: Mapped[bool] = mapped_column(Boolean, default=False)
    summonable: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(32), default="", server_default="")
    kit: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # basic/skills/ultimate/passive/mechanic
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # crit, crit_dmg, growth, range, role_name, appearance...


class PlayerHero(Base):
    __tablename__ = "player_heroes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    hero_code: Mapped[str] = mapped_column(ForeignKey("heroes.code"))
    level: Mapped[int] = mapped_column(Integer, default=1)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    shards: Mapped[int] = mapped_column(Integer, default=0)
    obtained_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "hero_code", name="uq_player_hero"),)

    hero: Mapped[Hero] = relationship()


class Formation(Base):
    __tablename__ = "formations"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True, default="campaign")
    slots: Mapped[list] = mapped_column(JSON, default=list)  # [player_hero_id|None] * 5
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- campaign & battles
class CampaignRegion(Base):
    __tablename__ = "campaign_regions"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    real_place: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class CampaignNode(Base):
    __tablename__ = "campaign_nodes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    region_code: Mapped[str] = mapped_column(ForeignKey("campaign_regions.code"))
    order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    territory: Mapped[str] = mapped_column(String(32))  # nature|cities|dungeons|...
    real_place: Mapped[str] = mapped_column(String(255), default="")
    enemies: Mapped[list] = mapped_column(JSON)  # [{hero_code, level, slot}]
    rewards: Mapped[dict] = mapped_column(JSON)  # {currency: amount}
    first_clear_rewards: Mapped[dict] = mapped_column(JSON, default=dict)
    map_pos: Mapped[list] = mapped_column(JSON, default=list)  # [q, r] hex coords
    is_boss: Mapped[bool] = mapped_column(Boolean, default=False)
    story: Mapped[list] = mapped_column(JSON, default=list)  # short portrait dialogues


class PlayerCampaignProgress(Base):
    __tablename__ = "player_campaign_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    node_code: Mapped[str] = mapped_column(ForeignKey("campaign_nodes.code"), primary_key=True)
    cleared_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    best_turns: Mapped[int | None] = mapped_column(Integer)


class Battle(Base):
    __tablename__ = "battles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    node_code: Mapped[str] = mapped_column(ForeignKey("campaign_nodes.code"))
    seed: Mapped[int] = mapped_column(BigInteger)
    team_snapshot: Mapped[list] = mapped_column(JSON)
    result: Mapped[str] = mapped_column(String(16))  # victory | defeat
    turns: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="simulated")  # simulated|completed|expired
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(TS)


# ---------------------------------------------------------------- economy
CURRENCIES = (
    "gold",
    "crystals",
    "summon_essence",
    "ancient_seals",
    "guild_marks",
    "nature_essence",
    "friend_tokens",
    "raid_tickets",
)


class Wallet(Base):
    __tablename__ = "wallets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(32), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)
    __mapper_args__ = {"version_id_col": version}


class WalletTransaction(Base):
    """Immutable ledger row. Never updated or deleted."""

    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    currency: Mapped[str] = mapped_column(String(32))
    delta: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class SummonPool(Base):
    __tablename__ = "summon_pools"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    rates: Mapped[dict] = mapped_column(JSON)  # {"1": 0.40, ...}
    cost: Mapped[dict] = mapped_column(JSON)  # {"summon_essence": 1} or {"crystals": 300}
    pity_threshold: Mapped[int] = mapped_column(Integer, default=60)
    pity_min_rarity: Mapped[int] = mapped_column(Integer, default=5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SummonHistory(Base):
    __tablename__ = "summon_history"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pool_code: Mapped[str] = mapped_column(ForeignKey("summon_pools.code"))
    hero_code: Mapped[str] = mapped_column(ForeignKey("heroes.code"))
    rarity: Mapped[int] = mapped_column(Integer)
    was_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    pity_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AfkClaim(Base):
    __tablename__ = "afk_claims"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[datetime] = mapped_column(TS)
    period_end: Mapped[datetime] = mapped_column(TS)
    seconds_credited: Mapped[int] = mapped_column(Integer)
    rewards: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class FortressBuilding(Base):
    __tablename__ = "fortress_buildings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------- quests & mail
class Quest(Base):
    __tablename__ = "quests"
    code: Mapped[str] = mapped_column(String(48), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # main|side|daily|personal|secret|seasonal
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    event: Mapped[str] = mapped_column(String(48))  # counter event name
    target: Mapped[int] = mapped_column(Integer, default=1)
    rewards: Mapped[dict] = mapped_column(JSON)
    order: Mapped[int] = mapped_column(Integer, default=0)
    requires: Mapped[str | None] = mapped_column(String(48))


class PlayerQuest(Base):
    __tablename__ = "player_quests"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    quest_code: Mapped[str] = mapped_column(ForeignKey("quests.code"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(TS)
    period: Mapped[str] = mapped_column(String(16), default="once")  # once | YYYY-MM-DD for daily


class MailMessage(Base):
    __tablename__ = "mail_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str | None] = mapped_column(String(48), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    attachments: Mapped[dict] = mapped_column(JSON, default=dict)
    sender: Mapped[str] = mapped_column(String(64), default="Крепость хранителей")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PlayerMail(Base):
    __tablename__ = "player_mail"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("mail_messages.id"))
    read_at: Mapped[datetime | None] = mapped_column(TS)
    claimed_at: Mapped[datetime | None] = mapped_column(TS)
    expires_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    message: Mapped[MailMessage] = relationship()


# ---------------------------------------------------------------- guilds
class Guild(Base):
    __tablename__ = "guilds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    tag: Mapped[str] = mapped_column(String(5), default="", server_default="")
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    emblem: Mapped[str] = mapped_column(String(32), default="stone", server_default="stone")
    join_mode: Mapped[str] = mapped_column(String(16), default="open", server_default="open")  # open|approval|invite
    min_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    leader_id: Mapped[str | None] = mapped_column(String(36), index=True)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # system virtual guild
    exp: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    treasury: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")  # guild resources (stone)
    specialization: Mapped[str | None] = mapped_column(String(32))
    week_points: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ai_policy: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # leader's AI switches
    settings: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # min_power, auto_accept, notify_chat


class GuildMember(Base):
    __tablename__ = "guild_members"
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(TS)
    warned_at: Mapped[datetime | None] = mapped_column(TS)
    contribution_week: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    contribution_total: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


class GuildContribution(Base):
    __tablename__ = "guild_contributions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GuildApplication(Base):
    __tablename__ = "guild_applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # application | invite
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|accepted|declined|cancelled
    invited_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GuildLog(Base):
    __tablename__ = "guild_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GuildUpgrade(Base):
    """Guild building or research level (kind = building | research)."""
    __tablename__ = "guild_upgrades"
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    level: Mapped[int] = mapped_column(Integer, default=0)


class GuildTask(Base):
    """Per-member daily guild task progress."""
    __tablename__ = "guild_tasks"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(36), index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)


class GuildExpedition(Base):
    __tablename__ = "guild_expeditions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | done
    participants: Mapped[list] = mapped_column(JSON, default=list)  # [{user_id, power}]
    started_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(TS)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class GuildWar(Base):
    __tablename__ = "guild_wars"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    guild_a: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    guild_b: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    score_a: Mapped[int] = mapped_column(Integer, default=0)
    score_b: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | finished
    winner: Mapped[str | None] = mapped_column(String(36))
    starts_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(TS)


class GuildWarAttack(Base):
    __tablename__ = "guild_war_attacks"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    war_id: Mapped[str] = mapped_column(ForeignKey("guild_wars.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    guild_id: Mapped[str] = mapped_column(String(36))
    target_user_id: Mapped[str] = mapped_column(String(36))
    result: Mapped[str] = mapped_column(String(16))
    points: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- AI population
class AiPersona(Base):
    __tablename__ = "ai_personas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    archetype: Mapped[str] = mapped_column(String(32))
    temperament: Mapped[dict] = mapped_column(JSON, default=dict)
    backstory: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    style: Mapped[str] = mapped_column(String(24), default="friendly", server_default="friendly")
    schedule: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")  # {"hours": [..], "tz_shift": n}
    interests: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    next_action_at: Mapped[datetime | None] = mapped_column(TS, index=True)
    last_action_at: Mapped[datetime | None] = mapped_column(TS)
    actions_today: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    day: Mapped[str] = mapped_column(String(10), default="", server_default="")


class AiActivityLog(Base):
    __tablename__ = "ai_activity_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("ai_personas.id", ondelete="CASCADE"), index=True)
    activity: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AiMemory(Base):
    __tablename__ = "ai_memory"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("ai_personas.id", ondelete="CASCADE"), index=True)
    subject_user_id: Mapped[str | None] = mapped_column(String(36))
    fact: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    expires_at: Mapped[datetime | None] = mapped_column(TS)


# ---------------------------------------------------------------- content / update system
class ContentPackage(Base):
    __tablename__ = "content_packages"
    package_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # heroes|textures|audio|ui|l10n|maps|balance...
    description: Mapped[str] = mapped_column(Text, default="")


class ContentPackageVersion(Base):
    """Immutable published build of a package (stored by SHA-256 in the content store)."""

    __tablename__ = "content_package_versions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("content_packages.package_id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128), default="")
    min_client_version: Mapped[str] = mapped_column(String(16), default="0.1.0")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    files: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("package_id", "version", name="uq_package_version"),)


class ContentManifestVersion(Base):
    __tablename__ = "content_manifest_versions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(16), index=True)  # dev|test|beta|stable
    platform: Mapped[str] = mapped_column(String(16), default="android")
    version: Mapped[int] = mapped_column(Integer)
    minimum_client_version: Mapped[str] = mapped_column(String(16), default="0.1.0")
    packages: Mapped[list] = mapped_column(JSON)  # [{package_id, version, size, sha256, url, dependencies}]
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("channel", "platform", "version", name="uq_manifest_version"),)


class ContentInstallation(Base):
    __tablename__ = "content_installations"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    manifest_version: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))  # ok | hash_mismatch | rolled_back
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- audit / admin
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (Index("ix_audit_action_time", "action", "created_at"),)


class AdminAction(Base):
    __tablename__ = "admin_actions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    admin: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- monetization (test mode by default)
class ShopProduct(Base):
    """Catalog row (seeded from content/monetization.json; admin edits are logged in catalog_changes)."""

    __tablename__ = "shop_products"
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    section: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    price_rub: Mapped[int] = mapped_column(Integer)  # kopecks; the real base price (discounts apply to it)
    discount_pct: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    contents: Mapped[dict] = mapped_column(JSON, default=dict)
    display: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    limit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    starts_at: Mapped[datetime | None] = mapped_column(TS)
    ends_at: Mapped[datetime | None] = mapped_column(TS)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    featured: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class CatalogChange(Base):
    __tablename__ = "catalog_changes"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    field: Mapped[str] = mapped_column(String(32))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String(64))  # admin:<name> | auto
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    reverted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    section: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|paid|fulfilled|refunded|failed|cancelled
    provider: Mapped[str] = mapped_column(String(16), default="test")  # test|rustore|google_play
    is_test: Mapped[bool] = mapped_column(Boolean, default=True)
    base_price_rub: Mapped[int] = mapped_column(Integer)
    price_rub: Mapped[int] = mapped_column(Integer)
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_txn_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    grant: Mapped[dict] = mapped_column(JSON, default=dict)  # exactly what was granted (for refunds)
    refund_debt: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    dispute: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(TS)
    fulfilled_at: Mapped[datetime | None] = mapped_column(TS)
    refunded_at: Mapped[datetime | None] = mapped_column(TS)


class Entitlement(Base):
    __tablename__ = "entitlements"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # subscription | cosmetic | bp_premium
    code: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(TS)
    order_id: Mapped[str | None] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(32), default="purchase", server_default="purchase")
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    __table_args__ = (Index("ix_entitlement_user_kind", "user_id", "kind", "code"),)


class SubscriptionClaim(Base):
    __tablename__ = "subscription_claims"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    rewards: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class VipXpLog(Base):
    __tablename__ = "vip_xp_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))  # purchase | daily | achievement | admin | refund
    ref: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class VipRewardClaim(Base):
    __tablename__ = "vip_reward_claims"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class BattlePassProgress(Base):
    __tablename__ = "battlepass_progress"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    premium: Mapped[bool] = mapped_column(Boolean, default=False)
    claimed_free: Mapped[list] = mapped_column(JSON, default=list)
    claimed_premium: Mapped[list] = mapped_column(JSON, default=list)


class PromoCode(Base):
    __tablename__ = "promo_codes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    rewards: Mapped[dict] = mapped_column(JSON, default=dict)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    uses: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(TS)
    ends_at: Mapped[datetime | None] = mapped_column(TS)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(64), default="admin")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"
    code: Mapped[str] = mapped_column(ForeignKey("promo_codes.code", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class LavkaPurchase(Base):
    __tablename__ = "lavka_purchases"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class DailyActivity(Base):
    __tablename__ = "daily_activity"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ServerSetting(Base):
    __tablename__ = "server_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(48))
    sku: Mapped[str | None] = mapped_column(String(64))
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (Index("ix_analytics_event_time", "event", "created_at"),)


# ---------------------------------------------------------------- social: friends, presence, gifts
class Friendship(Base):
    """Symmetric: one row per direction."""
    __tablename__ = "friendships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    friend_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="id")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class FriendRequest(Base):
    __tablename__ = "friend_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="id")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class FriendInvite(Base):
    __tablename__ = "friend_invites"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class FriendGift(Base):
    __tablename__ = "friend_gifts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    to_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(16), default="gift")  # gift | help
    contents: Mapped[dict] = mapped_column(JSON, default=dict)
    claimed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("from_id", "to_id", "day", "kind", name="uq_gift_daily"),)


class UserBlock(Base):
    __tablename__ = "user_blocks"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- raids & bosses
class RaidInstance(Base):
    __tablename__ = "raid_instances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # guild | world | seasonal | story
    boss_code: Mapped[str] = mapped_column(String(32))
    guild_id: Mapped[str | None] = mapped_column(String(36), index=True)
    stage: Mapped[int] = mapped_column(Integer, default=1)  # multi-stage raids
    hp_max: Mapped[int] = mapped_column(BigInteger)
    hp_left: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | defeated | expired
    starts_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(TS)
    defeated_at: Mapped[datetime | None] = mapped_column(TS)
    loot_done: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=0)
    __mapper_args__ = {"version_id_col": version}


class RaidAttack(Base):
    __tablename__ = "raid_attacks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    raid_id: Mapped[str] = mapped_column(ForeignKey("raid_instances.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    damage: Mapped[int] = mapped_column(BigInteger)
    phase: Mapped[int] = mapped_column(Integer, default=1)
    seed: Mapped[int] = mapped_column(BigInteger)
    team_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    lobby_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class RaidAttemptState(Base):
    __tablename__ = "raid_attempt_state"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    attempts: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class RaidLobby(Base):
    """Co-op raid: up to N players fight one boss together in one server-computed battle."""
    __tablename__ = "raid_lobbies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    boss_code: Mapped[str] = mapped_column(String(32))
    leader_id: Mapped[str] = mapped_column(String(36), index=True)
    members: Mapped[list] = mapped_column(JSON, default=list)  # [user_id]
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | done | cancelled
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class RaidLoot(Base):
    __tablename__ = "raid_loot"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    raid_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slot: Mapped[str] = mapped_column(String(24))  # base | rare:<item>
    item: Mapped[dict] = mapped_column(JSON, default=dict)
    rare: Mapped[bool] = mapped_column(Boolean, default=False)
    probability: Mapped[float] = mapped_column(Float, default=1.0)
    roll: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("raid_id", "user_id", "slot", name="uq_raid_loot"),)


# ---------------------------------------------------------------- arena
class ArenaSeason(Base):
    __tablename__ = "arena_seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(TS)
    ends_at: Mapped[datetime] = mapped_column(TS)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | closed
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class ArenaProfile(Base):
    __tablename__ = "arena_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, default=1000, index=True)
    best_rating: Mapped[int] = mapped_column(Integer, default=1000)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    def_wins: Mapped[int] = mapped_column(Integer, default=0)
    def_losses: Mapped[int] = mapped_column(Integer, default=0)
    defense: Mapped[list] = mapped_column(JSON, default=list)  # frozen unit snapshots
    defense_power: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    day: Mapped[str] = mapped_column(String(10), default="")
    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    training_used: Mapped[int] = mapped_column(Integer, default=0)
    season_id: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ArenaMatch(Base):
    __tablename__ = "arena_matches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    season_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="ranked")  # ranked | training
    attacker_id: Mapped[str] = mapped_column(String(36), index=True)
    defender_id: Mapped[str] = mapped_column(String(36), index=True)
    result: Mapped[str] = mapped_column(String(16))  # victory|defeat (attacker perspective)
    delta_att: Mapped[int] = mapped_column(Integer, default=0)
    delta_def: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int] = mapped_column(BigInteger)
    attacker_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    defender_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)


class SeasonResult(Base):
    """Permanent per-season history (arena, tournaments, raids, events) - never deleted at season end."""
    __tablename__ = "season_results"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(16))  # arena | tournament | raid | event
    season_id: Mapped[int] = mapped_column(Integer, default=0)
    ref: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "category", "season_id", "ref", name="uq_season_result"),)


# ---------------------------------------------------------------- tournaments
class Tournament(Base):
    __tablename__ = "tournaments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(48), unique=True)  # template + period, e.g. weekly_open:2026-W44
    template: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # individual | team | guild
    format: Mapped[str] = mapped_column(String(16))  # points | bracket | groups
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="registration")  # registration|running|finished
    reg_ends_at: Mapped[datetime] = mapped_column(TS)
    ends_at: Mapped[datetime] = mapped_column(TS)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class TournamentEntry(Base):
    __tablename__ = "tournament_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)  # player / captain / guild leader
    guild_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(48))
    members: Mapped[list] = mapped_column(JSON, default=list)  # [user_id]
    snapshot: Mapped[list] = mapped_column(JSON, default=list)  # frozen squads [[units...]]
    points: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    group_no: Mapped[int] = mapped_column(Integer, default=0)
    eliminated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    fights_used: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("tournament_id", "owner_id", name="uq_tournament_owner"),)


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(16), default="main")  # points | group | bracket
    a_entry: Mapped[str] = mapped_column(String(36))
    b_entry: Mapped[str | None] = mapped_column(String(36))
    winner_entry: Mapped[str | None] = mapped_column(String(36))
    seed: Mapped[int] = mapped_column(BigInteger, default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    played_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- chat & moderation
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(80))  # global | guild:<id> | dm:<a>:<b>
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)  # None = system
    text: Mapped[str] = mapped_column(String(400))
    reactions: Mapped[dict] = mapped_column(JSON, default=dict)  # emoji -> [user_id]
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (Index("ix_chat_channel_id", "channel", "id"),)


class ChatRead(Base):
    __tablename__ = "chat_reads"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_id: Mapped[int] = mapped_column(BigInteger, default=0)


class ChatReport(Base):
    __tablename__ = "chat_reports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    reporter_id: Mapped[str] = mapped_column(String(36), index=True)
    reason: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | actioned | dismissed
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("reporter_id", "message_id", "target_id", name="uq_report_once"),)


class Sanction(Base):
    __tablename__ = "sanctions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # warning | mute | temp_ban | perm_ban
    reason: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(16), default="moderator")  # auto | moderator
    starts_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(TS)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | revoked | expired
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    sanction_id: Mapped[int] = mapped_column(ForeignKey("sanctions.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | accepted | rejected
    resolution: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class SuspicionFlag(Base):
    """Anti-cheat signal. Never triggers a permanent ban by itself; moderators review."""
    __tablename__ = "suspicion_flags"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer, default=1)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | reviewed | dismissed
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- world events & state
class WorldEvent(Base):
    __tablename__ = "world_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(48), unique=True)  # template:period
    template: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    scale: Mapped[str] = mapped_column(String(16), default="weekly")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | finished
    starts_at: Mapped[datetime] = mapped_column(TS)
    ends_at: Mapped[datetime] = mapped_column(TS)
    goal: Mapped[int] = mapped_column(BigInteger)
    progress: Mapped[int] = mapped_column(BigInteger, default=0)
    outcome: Mapped[str | None] = mapped_column(String(16))  # success | failure
    choice_votes: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=0)
    __mapper_args__ = {"version_id_col": version}


class WorldEventContribution(Base):
    __tablename__ = "world_event_contrib"
    event_id: Mapped[str] = mapped_column(ForeignKey("world_events.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String(36), index=True)
    points: Mapped[int] = mapped_column(BigInteger, default=0)
    choice: Mapped[str | None] = mapped_column(String(32))
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)


class WorldState(Base):
    """Versioned world state. The highest version is current; any version can be restored by admins."""
    __tablename__ = "world_state"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- progression
class Achievement(Base):
    __tablename__ = "achievements"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(48), primary_key=True)
    achieved_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ReputationLog(Base):
    __tablename__ = "reputation_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    amount: Mapped[int] = mapped_column(Integer)
    day: Mapped[str] = mapped_column(String(10), index=True)
    ref: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class StatCounter(Base):
    """Permanent counters for achievements/records (never reset by seasons)."""
    __tablename__ = "stat_counters"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)


class JobRun(Base):
    """Scheduler lease + status per background job (safe with several API workers)."""
    __tablename__ = "job_runs"
    name: Mapped[str] = mapped_column(String(48), primary_key=True)
    lease_until: Mapped[datetime | None] = mapped_column(TS)
    last_run_at: Mapped[datetime | None] = mapped_column(TS)
    last_status: Mapped[str] = mapped_column(String(200), default="")
    runs: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- story (lore stage S2)
class StoryChoice(Base):
    """A decision the player made in a story scene. One row per choice; never changed afterwards."""
    __tablename__ = "story_choices"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    choice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    option: Mapped[str] = mapped_column(String(32))
    made_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class PlayerStoryFlag(Base):
    """Story facts derived from choices and events («timer_path=followed»). Read by later chapters and seasons."""
    __tablename__ = "player_story_flags"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    flag: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64), default="")
    set_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- caravan (lore stage S4)
class PlayerCaravan(Base):
    """Where the player's caravan stands or travels. Created on first access at the starting land."""
    __tablename__ = "player_caravans"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    location: Mapped[str] = mapped_column(String(32), default="r1_shikhany")
    destination: Mapped[str | None] = mapped_column(String(32))
    depart_at: Mapped[datetime | None] = mapped_column(TS)
    arrive_at: Mapped[datetime | None] = mapped_column(TS)
    trips: Mapped[int] = mapped_column(Integer, default=0)
