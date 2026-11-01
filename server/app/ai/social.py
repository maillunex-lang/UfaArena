"""Social system (stage 6): relationships of AI personas with other personas and real players — friendship,
sympathy, trust, rivalry, dislike, conflicts — kept between sessions; reputation; informal groups (circles of friends,
clubs, rival bands) that real players can join; it all feeds behaviour, speech and guild decisions."""
from __future__ import annotations

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AiPersona, AiRelationship, AiSocialGroup, AiSocialGroupMember, Friendship, PlayerProfile

# event -> (sympathy, trust, rivalry, dislike)
EFFECTS = {
    "chat": (0.03, 0.01, 0.0, -0.01), "dm": (0.05, 0.02, 0.0, -0.01), "friend": (0.25, 0.2, 0.0, -0.1),
    "gift": (0.08, 0.05, 0.0, -0.02), "arena_win": (0.0, 0.0, 0.05, 0.0), "arena_loss": (-0.01, 0.0, 0.08, 0.02),
    "guild_mate": (0.02, 0.03, 0.0, 0.0), "raid_together": (0.03, 0.04, 0.0, 0.0), "conflict": (-0.1, -0.05, 0.05, 0.12),
    "ignored": (-0.02, 0.0, 0.0, 0.0), "congrats": (0.04, 0.02, 0.0, 0.0), "help": (0.05, 0.05, 0.0, 0.0),
    "war_enemy": (-0.03, 0.0, 0.06, 0.04), "vote": (0.04, 0.04, 0.0, 0.0),
}
NAMES = {"sympathy": "Симпатия", "trust": "Доверие", "rivalry": "Соперничество", "dislike": "Неприязнь"}
GROUP_NAMES = ["Охотники Иремеля", "Клуб лучников", "Совет у костра", "Братство Курая", "Дозор Агидели", "Ночные беркуты",
               "Тропа шиханов", "Друзья кумыса", "Хранители легенд", "Стая Акбузата", "Северный ветер", "Звёздный аул"]
TOPICS = {"arena": "арена", "raid": "боссы", "story": "сюжет", "chat": "болтовня", "guild": "гильдии", "level": "прокачка"}


def _clamp(v: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, v)), 3)


def get(db: Session, subject_id: str, object_id: str, create: bool = True) -> AiRelationship | None:
    r = db.scalar(select(AiRelationship).where(AiRelationship.subject_id == subject_id, AiRelationship.object_id == object_id))
    if r is None and create and subject_id != object_id:
        r = AiRelationship(subject_id=subject_id, object_id=object_id, sympathy=0.0, trust=0.0, rivalry=0.0, dislike=0.0,
                           interactions=0, history=[], last_at=utcnow())
        db.add(r)
        db.flush()
    return r


def relate(db: Session, subject_id: str, object_id: str, kind: str, scale: float = 1.0) -> AiRelationship | None:
    """Applies an interaction to how `subject` (an AI persona's user id) feels about `object`."""
    if kind not in EFFECTS or not subject_id or not object_id or subject_id == object_id:
        return None
    r = get(db, subject_id, object_id)
    ds, dt, dr, dd = (x * scale for x in EFFECTS[kind])
    persona = db.scalar(select(AiPersona).where(AiPersona.user_id == subject_id))
    t = (persona.traits or {}) if persona else {}
    if kind in ("arena_loss", "conflict", "war_enemy") and t.get("temper", 0.5) > 0.6:
        dd *= 1.5  # hot-tempered personas hold grudges
    if kind in ("chat", "dm", "friend", "gift") and t.get("sociability", 0.5) > 0.6:
        ds *= 1.3
    r.sympathy = _clamp(r.sympathy + ds - dd * 0.3, -1, 1)
    r.trust = _clamp(r.trust + dt, 0, 1)
    r.rivalry = _clamp(r.rivalry * 0.995 + dr, 0, 1)
    r.dislike = _clamp(r.dislike * 0.995 + dd, 0, 1)
    r.interactions = (r.interactions or 0) + 1
    r.history = (list(r.history or []) + [{"at": utcnow().isoformat(), "kind": kind}])[-20:]
    r.last_at = utcnow()
    return r


def mutual(db: Session, a: str, b: str, kind: str) -> None:
    """Both sides feel it (only AI personas keep relationship rows; real players' feelings are their own)."""
    for s, o in ((a, b), (b, a)):
        if db.scalar(select(AiPersona.id).where(AiPersona.user_id == s)):
            relate(db, s, o, kind)


def label(r: AiRelationship | None) -> str:
    if r is None:
        return "незнакомы"
    if r.dislike > 0.5 and r.dislike > r.sympathy:
        return "неприязнь"
    if r.rivalry > 0.5:
        return "соперники" if r.sympathy >= 0 else "заклятые соперники"
    if r.sympathy > 0.6 and r.trust > 0.5:
        return "близкие друзья"
    if r.sympathy > 0.3:
        return "приятели"
    if r.sympathy < -0.3:
        return "не ладят"
    return "знакомые"


def reputation(db: Session, user_id: str) -> float:
    """How the AI community sees someone: average sympathy minus dislike from everyone who knows them (−1 … 1)."""
    row = db.execute(select(func.avg(AiRelationship.sympathy), func.avg(AiRelationship.dislike), func.count())
                     .where(AiRelationship.object_id == user_id)).one()
    if not row[2]:
        return 0.0
    return round(float(row[0] or 0) - 0.5 * float(row[1] or 0), 3)


def best_friends(db: Session, subject_id: str, limit: int = 3, real_only: bool = False) -> list[AiRelationship]:
    q = select(AiRelationship).where(AiRelationship.subject_id == subject_id, AiRelationship.sympathy > 0.3)
    if real_only:
        q = q.join(PlayerProfile, PlayerProfile.user_id == AiRelationship.object_id).where(PlayerProfile.is_ai.is_(False))
    return list(db.scalars(q.order_by(AiRelationship.sympathy.desc()).limit(limit)))


def who_likes(db: Session, object_id: str, min_sympathy: float = 0.3, limit: int = 10) -> list[AiRelationship]:
    """AI personas that like this player most (used to pick who writes first)."""
    return list(db.scalars(select(AiRelationship).where(AiRelationship.object_id == object_id,
                                                        AiRelationship.sympathy >= min_sympathy)
                           .order_by(AiRelationship.sympathy.desc()).limit(limit)))


# ------------------------------------------------------------------ informal groups
def group_of(db: Session, user_id: str) -> AiSocialGroup | None:
    return db.scalar(select(AiSocialGroup).join(AiSocialGroupMember, AiSocialGroupMember.group_id == AiSocialGroup.id)
                     .where(AiSocialGroupMember.user_id == user_id, AiSocialGroup.active.is_(True)))


def members(db: Session, group_id: str) -> list[str]:
    return list(db.scalars(select(AiSocialGroupMember.user_id).where(AiSocialGroupMember.group_id == group_id)))


def form_groups(db: Session, rng: random.Random, max_new: int = 1, max_groups: int = 25) -> int:
    """Personas who like each other gather into informal groups (3–6 members). Bounded work per run."""
    have = db.scalar(select(func.count()).select_from(AiSocialGroup).where(AiSocialGroup.active.is_(True))) or 0
    if have >= max_groups:
        return 0
    made = 0
    cands = list(db.scalars(select(AiRelationship).join(AiPersona, AiPersona.user_id == AiRelationship.subject_id)
                            .where(AiRelationship.sympathy >= 0.45, AiPersona.active.is_(True))
                            .order_by(AiRelationship.sympathy.desc()).limit(60)))
    rng.shuffle(cands)
    used: set[str] = set()
    for r in cands:
        if made >= max_new:
            break
        if r.subject_id in used or group_of(db, r.subject_id) is not None:
            continue
        core = [r.subject_id]
        for f in best_friends(db, r.subject_id, limit=6):
            if f.object_id not in used and group_of(db, f.object_id) is None:
                pf = db.get(PlayerProfile, f.object_id)
                if pf is not None and pf.is_ai:
                    core.append(f.object_id)
        if len(core) < 3:
            continue
        core = core[:6]
        founder = db.scalar(select(AiPersona).where(AiPersona.user_id == core[0]))
        topic = rng.choice([i for i in (founder.interests or []) if i in TOPICS] or list(TOPICS))
        name = rng.choice([n for n in GROUP_NAMES if not db.scalar(select(AiSocialGroup.id).where(AiSocialGroup.name == n))]
                          or GROUP_NAMES)
        g = AiSocialGroup(name=name, kind="club" if topic in ("arena", "raid") else "friends", founder_id=core[0], topic=topic,
                          created_at=utcnow(), active=True)
        db.add(g)
        db.flush()
        for i, uid in enumerate(core):
            db.add(AiSocialGroupMember(group_id=g.id, user_id=uid, role="founder" if i == 0 else "member", joined_at=utcnow()))
            used.add(uid)
        from . import memory as MEM
        for uid in core:
            p = db.scalar(select(AiPersona).where(AiPersona.user_id == uid))
            if p:
                MEM.add(db, p, "relationship", f"Вместе с друзьями собрали круг «{name}»", importance=2)
        made += 1
    db.flush()
    return made


def maybe_add_real_player(db: Session, group: AiSocialGroup, player_id: str) -> bool:
    """A real player who is friends with at least two members becomes part of the circle (stage 6)."""
    if db.get(AiSocialGroupMember, (group.id, player_id)) is not None:
        return False
    ids = members(db, group.id)
    friends = db.scalar(select(func.count()).select_from(Friendship).where(Friendship.user_id == player_id,
                                                                            Friendship.friend_id.in_(ids))) or 0
    if friends < 2:
        return False
    db.add(AiSocialGroupMember(group_id=group.id, user_id=player_id, role="member", joined_at=utcnow()))
    db.flush()
    return True
