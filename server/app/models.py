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
    afk_last_claim_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    summon_pity: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
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


# ---------------------------------------------------------------- guilds (later block)
class Guild(Base):
    __tablename__ = "guilds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GuildMember(Base):
    __tablename__ = "guild_members"
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class GuildContribution(Base):
    __tablename__ = "guild_contributions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    guild_id: Mapped[str] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


# ---------------------------------------------------------------- AI population (later block)
class AiPersona(Base):
    __tablename__ = "ai_personas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    archetype: Mapped[str] = mapped_column(String(32))
    temperament: Mapped[dict] = mapped_column(JSON, default=dict)
    backstory: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


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
