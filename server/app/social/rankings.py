"""Leaderboards (players, guilds, arena, raids, events, tournaments, reputation), social progression page
(achievements, reputation title, records, season history = permanent legacy). AI personas are excluded
from real-player boards and shown only on a separate, labelled AI board."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..models import (
    ArenaProfile, Guild, GuildMember, PlayerProfile, RaidAttack, ReputationLog, SeasonResult, StatCounter,
    WorldEvent, WorldEventContribution,
)
from . import progression as P
from .common import card, cfg, compute_power, league_of, rep_title

router = APIRouter(tags=["rankings"])
_cache: dict[str, tuple[float, list]] = {}
CATS = {"power": "Сила отряда", "arena": "Арена", "reputation": "Репутация", "guilds": "Гильдии",
        "raids": "Урон по боссам", "events": "Мировое событие", "tournaments": "Победы в турнирах", "ai": "ИИ-персонажи (отдельно)"}


def _board(db: Session, cat: str) -> list[dict]:
    hit = _cache.get(cat)
    if hit and time.monotonic() - hit[0] < 60:
        return hit[1]
    rows: list[dict] = []
    real = PlayerProfile.is_ai.is_(False)
    from ..ai.compete import PVP
    show_ai = PVP.get(db)["ai_in_rankings"]  # decision D-03: AI in common tables only when the admin enables it
    if cat == "power":
        q = select(PlayerProfile) if show_ai else select(PlayerProfile).where(real)
        for p in db.scalars(q.order_by(PlayerProfile.power.desc()).limit(100)):
            rows.append({"user_id": p.user_id, "name": p.nickname, "value": p.power, "level": p.level,
                         **({"is_ai": True} if p.is_ai else {})})
    elif cat == "ai":
        for p in db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True)).order_by(PlayerProfile.power.desc()).limit(100)):
            rows.append({"user_id": p.user_id, "name": p.nickname, "value": p.power, "level": p.level, "is_ai": True})
    elif cat == "arena":
        q = select(ArenaProfile) if show_ai else select(ArenaProfile).where(ArenaProfile.is_ai.is_(False))
        for ap in db.scalars(q.order_by(ArenaProfile.rating.desc()).limit(100)):
            rows.append({"user_id": ap.user_id, "name": card(db, ap.user_id)["nickname"], "value": ap.rating,
                         "extra": league_of(ap.rating)["name"], **({"is_ai": True} if ap.is_ai else {})})
    elif cat == "reputation":
        for p in db.scalars(select(PlayerProfile).where(real, PlayerProfile.reputation > 0).order_by(PlayerProfile.reputation.desc()).limit(100)):
            rows.append({"user_id": p.user_id, "name": p.nickname, "value": p.reputation, "extra": rep_title(p.reputation)})
    elif cat == "guilds":
        for g in db.scalars(select(Guild).order_by(Guild.level.desc(), Guild.exp.desc()).limit(100)):
            rows.append({"guild_id": g.id, "name": f"[{g.tag}] {g.name}", "value": g.level, "is_ai": g.is_ai,
                         "extra": f"{g.exp} опыта"})
        rows = [r for r in rows if not r["is_ai"]] + [r for r in rows if r["is_ai"]]  # virtual guilds listed after real ones
    elif cat == "raids":
        q = (select(StatCounter.user_id, StatCounter.value).join(PlayerProfile, PlayerProfile.user_id == StatCounter.user_id)
             .where(StatCounter.key == "raid_damage", real).order_by(StatCounter.value.desc()).limit(100))
        for uid, v in db.execute(q).all():
            rows.append({"user_id": uid, "name": card(db, uid)["nickname"], "value": int(v)})
    elif cat == "events":
        ev = db.scalar(select(WorldEvent).order_by(WorldEvent.starts_at.desc()))
        if ev:
            for c in db.scalars(select(WorldEventContribution).where(WorldEventContribution.event_id == ev.id)
                                .order_by(WorldEventContribution.points.desc()).limit(100)):
                rows.append({"user_id": c.user_id, "name": card(db, c.user_id)["nickname"], "value": int(c.points), "extra": ev.name})
    elif cat == "tournaments":
        wins: dict[str, int] = {}
        for r in db.scalars(select(SeasonResult).where(SeasonResult.category == "tournament")):
            if (r.result or {}).get("place") == 1:
                wins[r.user_id] = wins.get(r.user_id, 0) + 1
        for uid, v in sorted(wins.items(), key=lambda x: -x[1])[:100]:
            rows.append({"user_id": uid, "name": card(db, uid)["nickname"], "value": v})
    else:
        raise GameError("not_found", "Нет такого рейтинга", 404)
    rank = 0
    for r in rows:
        if r.get("is_ai") and cat in ("power", "arena"):
            r["rank"] = None  # AI shown with the label, without a place (D-03)
        else:
            rank += 1
            r["rank"] = rank
    _cache[cat] = (time.monotonic(), rows)
    return rows


@router.get("/rankings/{cat}")
def rankings(cat: str, offset: int = Query(0, ge=0, le=100), user: CurrentUser = Depends(player),
             db: Session = Depends(get_db)):
    compute_power(db, user.id)
    db.commit()
    rows = _board(db, cat)
    me = next((r for r in rows if r.get("user_id") == user.id), None)
    if cat == "guilds":
        m = db.scalar(select(GuildMember).where(GuildMember.user_id == user.id))
        me = next((r for r in rows if m and r.get("guild_id") == m.guild_id), None)
    return {"category": cat, "title": CATS.get(cat, cat), "categories": CATS, "items": rows[offset:offset + 50],
            "me": me, "note": "ИИ-персонажи не участвуют в рейтингах игроков" if cat != "ai" else "Отдельный рейтинг ИИ-персонажей"}


@router.get("/progression")
def progression(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    ach = P.achievements_view(db, user.id)
    hist = [{"category": r.category, "season": r.season_id, "result": r.result, "at": as_utc(r.created_at).isoformat()}
            for r in db.scalars(select(SeasonResult).where(SeasonResult.user_id == user.id).order_by(SeasonResult.id.desc()).limit(40))]
    ap = db.get(ArenaProfile, user.id)
    best_hit = db.scalar(select(func.max(RaidAttack.damage)).where(RaidAttack.user_id == user.id)) or 0
    rep_log = [{"kind": r.kind, "amount": r.amount, "at": as_utc(r.created_at).isoformat()}
               for r in db.scalars(select(ReputationLog).where(ReputationLog.user_id == user.id).order_by(ReputationLog.id.desc()).limit(15))]
    titles = cfg()["progression"]["titles"]
    nxt = next((t for t in titles if t["min"] > (p.reputation or 0)), None)
    from ..monetization.battlepass import view as bp_view
    try:
        bp = bp_view(db, user.id)
        season = {"name": bp.get("name"), "ends": bp.get("ends"), "level": bp.get("level")}
    except Exception:
        season = None
    return {
        "reputation": p.reputation or 0, "title": rep_title(p.reputation or 0),
        "next_title": nxt, "reputation_sources": cfg()["progression"]["reputation"],
        "reputation_caps": cfg()["progression"]["reputation_daily_cap"], "reputation_log": rep_log,
        "achievements": ach["items"], "stats": ach["stats"],
        "records": {"best_arena_rating": ap.best_rating if ap else None, "best_raid_hit": int(best_hit),
                    "tournament_wins": sum(1 for h in hist if h["category"] == "tournament" and (h["result"] or {}).get("place") == 1),
                    "events_joined": sum(1 for h in hist if h["category"] == "event")},
        "legacy": hist, "season": season,
        "note": "Достижения, репутация и история сезонов постоянны и не сбрасываются в конце сезона.",
    }
