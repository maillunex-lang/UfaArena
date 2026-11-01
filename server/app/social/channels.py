"""Extra chat channels (Living World AI stage 8, decision D-11) — a game feature for everyone, not only AI:

* `region:<code>`  — regional channel of the land where the player's caravan stands;
* `event:<id>`     — channel of the active world event (exists while the event runs);
* `alliance:<id>`  — shared chat of a guild alliance (D-12);
* `group:<id>`     — chat of an informal circle the player belongs to (AI circles real players can join);
* `news`           — announcements: read-only for players, written by the administration.
Each kind is switched on/off in the admin panel (section "Каналы"); AI participation per channel kind too."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.sections import Section
from ..game import data as D
from ..models import (
    AiSocialGroup, AiSocialGroupMember, GuildAllianceMember, GuildAlliance, GuildMember, PlayerCaravan, WorldEvent,
)

KINDS = ("global", "guild", "region", "event", "alliance", "group", "news", "dm")
KIND_NAMES = {"global": "Общий чат", "guild": "Чат гильдии", "region": "Региональные каналы", "event": "Каналы событий",
              "alliance": "Чат союза гильдий", "group": "Чаты неформальных групп", "news": "Объявления",
              "dm": "Личные сообщения"}

SECTION = Section(
    "ai_channels",
    {"region_enabled": True, "event_enabled": True, "alliance_enabled": True, "group_enabled": True, "news_enabled": True,
     "ai_global": True, "ai_guild": True, "ai_region": True, "ai_event": True, "ai_alliance": True, "ai_group": True,
     "ai_dm_first": True, "ai_invites": True},
    {k: ("bool",) for k in ("region_enabled", "event_enabled", "alliance_enabled", "group_enabled", "news_enabled",
                            "ai_global", "ai_guild", "ai_region", "ai_event", "ai_alliance", "ai_group", "ai_dm_first",
                            "ai_invites")},
    {"region_enabled": "Региональные каналы (для всех игроков)", "event_enabled": "Каналы событий (для всех)",
     "alliance_enabled": "Чат союза гильдий", "group_enabled": "Чаты неформальных групп",
     "news_enabled": "Канал «Объявления»", "ai_global": "ИИ пишут в общий чат", "ai_guild": "ИИ пишут в чаты гильдий",
     "ai_region": "ИИ пишут в региональные каналы", "ai_event": "ИИ обсуждают события в каналах событий",
     "ai_alliance": "ИИ пишут в чаты союзов", "ai_group": "ИИ пишут в чаты групп",
     "ai_dm_first": "ИИ могут первыми писать игрокам в личные", "ai_invites": "ИИ могут приглашать игроков (гильдии, события)"})


def kind_of(channel: str) -> str:
    return channel.split(":", 1)[0] if ":" in channel else channel


def region_name(code: str) -> str:
    for r in D.REGIONS:
        if r["code"] == code:
            return r["name"]
    return code


def region_of(db: Session, user_id: str) -> str:
    c = db.get(PlayerCaravan, user_id)
    return (c.location if c and c.location else "r1_shikhany")


def ai_region(persona) -> str:
    """AI personas have a home land (stable per persona) for regional chat."""
    lands = sorted({a for a, b in D.ROADS} | {b for a, b in D.ROADS})
    code = (persona.counters or {}).get("region")
    if code in lands:
        return code
    return lands[sum(map(ord, persona.id)) % len(lands)]


def active_event(db: Session) -> WorldEvent | None:
    return db.scalar(select(WorldEvent).where(WorldEvent.status == "active").order_by(WorldEvent.starts_at.desc()))


def alliance_of_user(db: Session, user_id: str) -> GuildAlliance | None:
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
    if m is None:
        return None
    am = db.get(GuildAllianceMember, m.guild_id)
    return db.get(GuildAlliance, am.alliance_id) if am else None


def groups_of(db: Session, user_id: str) -> list[AiSocialGroup]:
    return list(db.scalars(select(AiSocialGroup).join(AiSocialGroupMember, AiSocialGroupMember.group_id == AiSocialGroup.id)
                           .where(AiSocialGroupMember.user_id == user_id, AiSocialGroup.active.is_(True))))


def extra_channels(db: Session, user_id: str) -> list[dict]:
    s = SECTION.get(db)
    out = []
    if s["news_enabled"]:
        out.append({"channel": "news", "name": "Объявления", "kind": "news", "read_only": True})
    if s["region_enabled"]:
        code = region_of(db, user_id)
        out.append({"channel": f"region:{code}", "name": "Регион: " + region_name(code), "kind": "region"})
    if s["event_enabled"]:
        ev = active_event(db)
        if ev is not None:
            out.append({"channel": f"event:{ev.id}", "name": "Событие: " + ev.name, "kind": "event"})
    if s["alliance_enabled"]:
        a = alliance_of_user(db, user_id)
        if a is not None:
            out.append({"channel": f"alliance:{a.id}", "name": "Союз: " + a.name, "kind": "alliance"})
    if s["group_enabled"]:
        for g in groups_of(db, user_id)[:3]:
            out.append({"channel": f"group:{g.id}", "name": "Круг: " + g.name, "kind": "group"})
    return out


def can_read(db: Session, user_id: str, channel: str) -> bool:
    k = kind_of(channel)
    s = SECTION.get(db)
    if k == "news":
        return bool(s["news_enabled"])
    if k == "region":
        return bool(s["region_enabled"]) and channel == f"region:{region_of(db, user_id)}"
    if k == "event":
        ev = active_event(db)
        return bool(s["event_enabled"]) and ev is not None and channel == f"event:{ev.id}"
    if k == "alliance":
        a = alliance_of_user(db, user_id)
        return bool(s["alliance_enabled"]) and a is not None and channel == f"alliance:{a.id}"
    if k == "group":
        return bool(s["group_enabled"]) and any(channel == f"group:{g.id}" for g in groups_of(db, user_id))
    return False


def can_write(db: Session, user_id: str, channel: str) -> bool:
    return kind_of(channel) != "news" and can_read(db, user_id, channel)


def ai_may_post(db: Session, channel: str) -> bool:
    k = kind_of(channel)
    if k == "dm":
        return True
    s = SECTION.get(db)
    return bool(s.get(f"ai_{k}", False))


def ai_member_ids(db: Session, channel: str) -> list[str] | None:
    """Who may speak in a members-only channel (guild / alliance / group); None for open channels."""
    k = kind_of(channel)
    ref = channel.split(":", 1)[1] if ":" in channel else ""
    if k == "guild":
        return list(db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == ref)))
    if k == "alliance":
        gids = list(db.scalars(select(GuildAllianceMember.guild_id).where(GuildAllianceMember.alliance_id == ref)))
        return list(db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id.in_(gids)))) if gids else []
    if k == "group":
        return list(db.scalars(select(AiSocialGroupMember.user_id).where(AiSocialGroupMember.group_id == ref)))
    return None


def readers_online(db: Session, channel: str, minutes: int = 15) -> bool:
    """AI talk only where a real player can read it now."""
    from datetime import timedelta
    from ..core.db import utcnow
    from ..models import PlayerProfile
    since = utcnow() - timedelta(minutes=minutes)
    q = select(PlayerProfile.user_id).where(PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)
    k = kind_of(channel)
    if k == "region":
        q = q.join(PlayerCaravan, PlayerCaravan.user_id == PlayerProfile.user_id).where(
            PlayerCaravan.location == channel.split(":", 1)[1])
    else:
        ids = ai_member_ids(db, channel)
        if ids is not None:
            q = q.where(PlayerProfile.user_id.in_(ids))
    return db.scalar(q.limit(1)) is not None
