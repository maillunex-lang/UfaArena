"""Shared helpers for the online systems: config, presence, public profile cards, frozen squads,
reward delivery. Everything is computed on the server; the client only renders results."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_engine, utcnow
from ..core.errors import GameError
from ..game import roster as R
from ..game.battle_sim import MAX_TIME, Simulation, hero_stats, make_unit, power_rating
from ..models import (
    ArenaProfile, Formation, Guild, GuildMember, Hero, PlayerHero, PlayerProfile, User,
)
from ..services import grant, hero_dict, team_bonuses

PATH = Path(__file__).resolve().parents[1] / "game" / "content" / "social.json"
FACTION_ADV = R.advantage()


@lru_cache
def cfg() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def day(now: datetime | None = None) -> str:
    return (now or utcnow()).strftime("%Y-%m-%d")


def week_key(now: datetime | None = None) -> str:
    y, w, _ = (now or utcnow()).isocalendar()
    return f"{y}-W{w:02d}"


def month_key(now: datetime | None = None) -> str:
    return (now or utcnow()).strftime("%Y-%m")


def profile(db: Session, user_id: str) -> PlayerProfile:
    p = db.get(PlayerProfile, user_id)
    if p is None:
        raise GameError("not_found", "Игрок не найден", 404)
    return p


def by_public_id(db: Session, uralia_id: str) -> PlayerProfile:
    p = db.scalar(select(PlayerProfile).where(PlayerProfile.uralia_id == uralia_id.strip().upper()))
    if p is None:
        raise GameError("not_found", "Игрок с таким ID не найден", 404)
    return p


# ------------------------------------------------------------------ presence
_touch_cache: dict[str, float] = {}


def touch(user_id: str) -> None:
    """Marks the player online. Throttled to one DB write per minute per player."""
    now = time.monotonic()
    if now - _touch_cache.get(user_id, -1e9) < 60:
        return
    _touch_cache[user_id] = now
    try:
        with Session(get_engine()) as db:
            p = db.get(PlayerProfile, user_id)
            if p is not None:
                p.last_seen_at = utcnow()
                db.commit()
    except Exception:  # presence must never break gameplay requests
        pass


def presence(p: PlayerProfile, viewer_is_self: bool = False) -> str:
    """online | recent | offline | hidden. AI personas report their simulated schedule."""
    if p.presence_hidden and not viewer_is_self:
        return "hidden"
    if p.last_seen_at is None:
        return "offline"
    age = (utcnow() - as_utc(p.last_seen_at)).total_seconds() / 60
    c = cfg()["friends"]
    if age <= c["online_minutes"]:
        return "online"
    if age <= c["recent_minutes"]:
        return "recent"
    return "offline"


# ------------------------------------------------------------------ squads
def compute_power(db: Session, user_id: str) -> int:
    b = team_bonuses(db, user_id)
    vals = []
    for ph in db.scalars(select(PlayerHero).where(PlayerHero.user_id == user_id)):
        vals.append(power_rating(hero_stats(hero_dict(ph.hero), ph.level, ph.stars, **b)))
    pw = sum(sorted(vals, reverse=True)[:5])
    p = db.get(PlayerProfile, user_id)
    if p is not None and p.power != pw:
        p.power = pw
    return pw


def formation_slots(db: Session, user_id: str) -> list[str | None]:
    f = db.scalar(select(Formation).where(Formation.user_id == user_id, Formation.kind == "campaign"))
    return list(f.slots) if f else [None] * 5


def freeze_squad(db: Session, user_id: str, slots: list[str | None] | None = None, extra: dict | None = None) -> list[dict]:
    """Frozen copy of a squad (stats included) for defense teams, tournaments and replays."""
    slots = slots if slots is not None else formation_slots(db, user_id)
    if len(slots) != 5:
        raise GameError("bad_slots", "Отряд — ровно 5 слотов")
    b = dict(team_bonuses(db, user_id))
    for k, v in (extra or {}).items():
        b[k] = b.get(k, 0) + v
    ids = [s for s in slots if s]
    if len(ids) != len(set(ids)):
        raise GameError("duplicate_hero", "Герой не может стоять в двух слотах")
    out = []
    for slot, pid in enumerate(slots):
        if not pid:
            continue
        ph = db.get(PlayerHero, pid)
        if ph is None or ph.user_id != user_id:
            raise GameError("not_owned", "Отряд содержит чужого героя", 403)
        st = hero_stats(hero_dict(ph.hero), ph.level, ph.stars, atk_pct=b.get("atk_pct", 0), hp_pct=b.get("hp_pct", 0),
                        def_pct=b.get("def_pct", 0))
        out.append({"slot": slot, "hero_code": ph.hero_code, "level": ph.level, "stars": ph.stars,
                    "rarity": ph.hero.rarity, "faction": ph.hero.faction_code, "class": ph.hero.class_code,
                    "stats": st, "power": power_rating(st)})
    if not out:
        raise GameError("empty_formation", "Нужен хотя бы один герой")
    return out


def squad_power(spec: list[dict]) -> int:
    return sum(int(u.get("power", 0)) for u in spec)


def check_rules(spec: list[dict], rules: dict) -> None:
    if rules.get("max_rarity") and any(int(u["rarity"]) > int(rules["max_rarity"]) for u in spec):
        raise GameError("rules", "Правила турнира: только герои до редкости %d" % int(rules["max_rarity"]))
    if rules.get("one_faction") and len({u["faction"] for u in spec}) > 1:
        raise GameError("rules", "Правила турнира: все герои отряда одной фракции")


def units_from_spec(db: Session, spec: list[dict], side: int, stat_mult: dict | None = None) -> list:
    units = []
    for u in spec:
        h = db.get(Hero, u["hero_code"])
        if h is None:
            continue
        st = dict(u["stats"])
        for k, m in (stat_mult or {}).items():
            st[k] = int(st[k] * m)
        unit = make_unit(side, int(u["slot"]), hero_dict(h), st, int(u["level"]), FACTION_ADV.get(h.faction_code))
        unit.skill_level = 1 + int(u.get("stars", 0))
        units.append(unit)
    return units


def run_battle(team: list, enemies: list, seed: int, max_time: float | None = None) -> tuple[dict, Simulation]:
    initial_sim = Simulation(team, enemies, seed)
    if max_time:
        initial_sim.max_time = max_time
    units = [u.public() for u in initial_sim.units]
    out = initial_sim.run()
    out.update(units=units, seed=seed, realtime=True, engine=3)
    return out, initial_sim


def pvp(db: Session, att: list[dict], dfn: list[dict], seed: int, stat_mult: dict | None = None) -> dict:
    sim, _ = run_battle(units_from_spec(db, att, 0, stat_mult), units_from_spec(db, dfn, 1, stat_mult), seed)
    return sim


def summary(sim: dict) -> dict:
    """Compact battle summary (full replays are re-simulated deterministically from seed + snapshots)."""
    return {"result": sim["result"], "duration": sim["duration"], "timeout": sim.get("timeout", False),
            "survivors": sim.get("survivors", [])}


# ------------------------------------------------------------------ public cards
def guild_of(db: Session, user_id: str) -> Guild | None:
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
    return db.get(Guild, m.guild_id) if m else None


def rep_title(rep: int) -> str:
    name = ""
    for t in cfg()["progression"]["titles"]:
        if rep >= t["min"]:
            name = t["name"]
    return name


def league_of(rating: int) -> dict:
    lg = cfg()["arena"]["leagues"][0]
    for x in cfg()["arena"]["leagues"]:
        if rating >= x["min"]:
            lg = x
    return {"code": lg["code"], "name": lg["name"]}


def card(db: Session, user_id: str, viewer_id: str | None = None) -> dict:
    p = profile(db, user_id)
    g = guild_of(db, user_id)
    ap = db.get(ArenaProfile, user_id)
    return {
        "user_id": user_id, "uralia_id": p.uralia_id, "nickname": p.nickname, "level": p.level,
        "avatar": p.avatar or "", "is_ai": bool(p.is_ai), "power": p.power or compute_power(db, user_id),
        "presence": presence(p, viewer_id == user_id), "reputation": p.reputation or 0,
        "rep_title": rep_title(p.reputation or 0), "vip_level": 0 if p.is_ai else (p.vip_level or 0),
        "guild": {"id": g.id, "name": g.name, "tag": g.tag, "is_ai": g.is_ai} if g else None,
        "arena": {"rating": ap.rating, "league": league_of(ap.rating)["name"]} if ap else None,
        "cosmetics": {k: v for k, v in (p.cosmetics or {}).items() if k in ("frame", "title", "avatar_fx")},
    }


def is_ai(db: Session, user_id: str) -> bool:
    p = db.get(PlayerProfile, user_id)
    return bool(p and p.is_ai)


def is_banned(db: Session, user_id: str) -> bool:
    u = db.get(User, user_id)
    return bool(u and u.is_banned)


# ------------------------------------------------------------------ rewards
def give(db: Session, user_id: str, reward: dict, reason: str, ref: str | None = None) -> dict:
    """Currencies through the ledger; earn-only cosmetics as permanent entitlements."""
    reward = dict(reward or {})
    cos = reward.pop("cosmetic", None)
    cur = {k: int(v) for k, v in reward.items() if int(v) > 0}
    out = grant(db, user_id, cur, reason, ref) if cur else {}
    out = dict(out)
    if cos:
        from ..monetization.config import cosmetic
        from ..monetization.fulfill import _entitle
        if cosmetic(cos):
            _entitle(db, user_id, "cosmetic", cos, None, None, reason[:16], {})
            out["cosmetic"] = cos
    return out


def scale_reward(reward: dict, mult: float) -> dict:
    return {k: (int(v * mult) if isinstance(v, (int, float)) else v) for k, v in reward.items()}


def ensure_since(dt: datetime | None, minutes: float) -> bool:
    return dt is None or (utcnow() - as_utc(dt)) >= timedelta(minutes=minutes)


__all__ = ["cfg", "day", "week_key", "month_key", "card", "freeze_squad", "pvp", "give", "MAX_TIME"]


def notify(db: Session, user_id: str, title: str, body: str, rewards: dict | None = None,
           sender: str = "Курултай") -> None:
    """In-game mail. Currency rewards are claimable attachments; cosmetics are granted right away."""
    from ..models import MailMessage, PlayerMail
    p = db.get(PlayerProfile, user_id)
    if p is None or p.is_ai:
        return
    rewards = dict(rewards or {})
    cos = rewards.pop("cosmetic", None)
    if cos:
        give(db, user_id, {"cosmetic": cos}, "reward_cosmetic")
        body += "\nКосметика добавлена в гардероб."
    msg = MailMessage(title=title[:128], body=body, attachments={k: int(v) for k, v in rewards.items() if int(v) > 0},
                      sender=sender)
    db.add(msg)
    db.flush()
    db.add(PlayerMail(user_id=user_id, message_id=msg.id, expires_at=utcnow() + timedelta(days=30)))
    db.flush()


def blocked_ids(db: Session, user_id: str) -> set[str]:
    from ..models import UserBlock
    return set(db.scalars(select(UserBlock.blocked_id).where(UserBlock.user_id == user_id)))
