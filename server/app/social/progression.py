"""Permanent social progression: stat counters, achievements, reputation (with daily caps against farming),
and the central event hook that feeds guild tasks, world events and achievements from gameplay."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Achievement, PlayerProfile, ReputationLog, StatCounter
from .common import cfg, day, give

# gameplay event -> (stat counters, reputation kind, guild task code, world-event points key)
EVENT_MAP: dict[str, dict] = {
    "battle_win": {"stats": ["battles"], "guild_task": "g_battles", "event": "battle_win"},
    "battle_loss": {"stats": ["battles"], "guild_task": "g_battles", "event": "battle"},
    "afk_claim": {"event": "afk_claim"},
    "quest_claim": {"event": "quest"},
    "gift_sent": {"stats": ["gifts_sent"], "rep": "gift", "event": "gift"},
    "help": {"stats": ["helps"], "rep": "help", "guild_task": "g_help", "event": "help"},
    "raid_attack": {"stats": ["raid_attacks"], "rep": "raid", "guild_task": "g_boss"},
    "arena_win": {"stats": ["arena_wins"], "rep": "arena_win", "event": "arena"},
    "arena_loss": {"event": "arena"},
    "tournament_join": {"stats": ["tournaments"], "rep": "tournament"},
    "chat_meaningful": {"stats": ["chat_meaningful"], "rep": "chat"},
    "guild_donate": {"guild_task": "g_donate"},
    "guild_task": {"rep": "guild_task"},
}


def add_stat(db: Session, user_id: str, key: str, amount: int = 1, absolute: int | None = None) -> int:
    sc = db.get(StatCounter, (user_id, key))
    if sc is None:
        sc = StatCounter(user_id=user_id, key=key, value=0)
        db.add(sc)
    sc.value = absolute if absolute is not None else (sc.value or 0) + amount
    db.flush()
    check_achievements(db, user_id, key, sc.value)
    return sc.value


def stats(db: Session, user_id: str) -> dict[str, int]:
    return {s.key: s.value for s in db.scalars(select(StatCounter).where(StatCounter.user_id == user_id))}


def check_achievements(db: Session, user_id: str, key: str, value: int) -> list[str]:
    got = []
    prof = db.get(PlayerProfile, user_id)
    for code, a in cfg()["progression"]["achievements"].items():
        if a["stat"] != key or value < a["goal"] or db.get(Achievement, (user_id, code)):
            continue
        db.add(Achievement(user_id=user_id, code=code))
        db.flush()
        if prof is not None and not prof.is_ai:
            give(db, user_id, a.get("reward", {}), "achievement", code)
        got.append(code)
    return got


def reputation(db: Session, user_id: str, kind: str, ref: str | None = None) -> int:
    amount = int(cfg()["progression"]["reputation"].get(kind, 0))
    if amount <= 0:
        return 0
    cap = cfg()["progression"]["reputation_daily_cap"].get(kind)
    d = day()
    if cap is not None:
        today = db.scalar(select(func.coalesce(func.sum(ReputationLog.amount), 0)).where(
            ReputationLog.user_id == user_id, ReputationLog.kind == kind, ReputationLog.day == d)) or 0
        if today >= cap:
            return 0
        amount = min(amount, cap - today)
    db.add(ReputationLog(user_id=user_id, kind=kind, amount=amount, day=d, ref=ref))
    p = db.get(PlayerProfile, user_id)
    if p is not None:
        p.reputation = (p.reputation or 0) + amount
    db.flush()
    return amount


def on(db: Session, user_id: str, event: str, amount: int = 1, ref: str | None = None) -> None:
    """Single entry point for social side effects of gameplay. Runs in the caller's transaction."""
    m = EVENT_MAP.get(event, {})
    for st in m.get("stats", []):
        add_stat(db, user_id, st, amount if event not in ("battle_win", "battle_loss") else 1)
    if m.get("rep"):
        reputation(db, user_id, m["rep"], ref)
    if m.get("guild_task"):
        from .guilds import task_progress
        task_progress(db, user_id, m["guild_task"], 1)
    if m.get("event"):
        from .events import contribute
        contribute(db, user_id, cfg()["events"]["points"].get(m["event"], 0))
    if event == "raid_attack":
        add_stat(db, user_id, "raid_damage", amount)
        from .events import contribute
        contribute(db, user_id, amount // int(cfg()["events"]["points"]["raid_damage_per"]))


def achievements_view(db: Session, user_id: str) -> dict:
    have = {a.code: a.achieved_at for a in db.scalars(select(Achievement).where(Achievement.user_id == user_id))}
    st = stats(db, user_id)
    items = []
    for code, a in cfg()["progression"]["achievements"].items():
        items.append({"code": code, "name": a["name"], "desc": a["desc"], "goal": a["goal"],
                      "progress": min(a["goal"], st.get(a["stat"], 0)), "reward": a.get("reward", {}),
                      "done": code in have, "at": have[code].isoformat() if code in have else None})
    return {"items": items, "stats": st}
