"""World events (weekly + monthly): server-wide goals fed by gameplay, personal / guild / server progress,
choices by vote, and permanent consequences in a versioned world state that admins can restore."""
from __future__ import annotations

import copy
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import (
    CampaignNode, Guild, GuildMember, Hero, PlayerProfile, SeasonResult, StatCounter, WorldEvent,
    WorldEventContribution, WorldState,
)
from ..services import hero_dict, wallet_dict
from .common import FACTION_ADV, card, cfg, day, freeze_squad, give, notify, run_battle, units_from_spec

router = APIRouter(prefix="/events", tags=["events"])
EVENT_BATTLES_PER_DAY = 5


def E() -> dict:
    return cfg()["events"]


# ------------------------------------------------------------------ world state
DEFAULT_STATE = {"regions": {}, "unlocked": [], "story": [], "decor": [], "chronicle": []}


def world(db: Session) -> WorldState:
    ws = db.scalar(select(WorldState).order_by(WorldState.version.desc()))
    if ws is None:
        ws = WorldState(version=1, state=copy.deepcopy(DEFAULT_STATE), reason="Начало мира")
        db.add(ws)
        db.flush()
    return ws


def change_world(db: Session, reason: str, fn) -> WorldState:
    cur = world(db)
    st = copy.deepcopy(cur.state)
    fn(st)
    ws = WorldState(version=cur.version + 1, state=st, reason=reason[:120])
    db.add(ws)
    db.flush()
    return ws


def restore_world(db: Session, version: int, who: str) -> WorldState:
    old = db.get(WorldState, version)
    if old is None:
        raise GameError("not_found", "Нет такой версии мира", 404)
    return change_world(db, f"Восстановление версии {version} ({who})", lambda st: (st.clear(), st.update(copy.deepcopy(old.state))))


def region_status(db: Session, region_code: str) -> str | None:
    return world(db).state.get("regions", {}).get(region_code)


# ------------------------------------------------------------------ schedule
def _period(scale: str, now: datetime) -> tuple[datetime, str, int]:
    if scale == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        y, w, _ = start.isocalendar()
        return start, f"{y}-W{w:02d}", w
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, start.strftime("%Y-%m"), start.month


def ensure(db: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    plan = []
    s, key, w = _period("weekly", now)
    rot = E()["weekly_rotation"]
    plan.append((rot[w % len(rot)], s, key))
    s, key, _ = _period("monthly", now)
    plan.append((E()["monthly"], s, key))
    for tpl_code, start, key in plan:
        code = f"{tpl_code}:{key}"
        if db.scalar(select(WorldEvent).where(WorldEvent.code == code)):
            continue
        tpl = E()["templates"][tpl_code]
        ends = start + timedelta(days=tpl["days"])
        if ends <= now:
            continue
        try:
            with db.begin_nested():
                db.add(WorldEvent(code=code, template=tpl_code, name=tpl["name"], kind=tpl["kind"], scale=tpl["scale"],
                                  starts_at=start, ends_at=ends, goal=tpl["goal"], progress=0, choice_votes={}))
        except IntegrityError:
            pass


def active_events(db: Session) -> list[WorldEvent]:
    now = utcnow()
    return list(db.scalars(select(WorldEvent).where(WorldEvent.status == "active", WorldEvent.starts_at <= now,
                                                    WorldEvent.ends_at > now)))


def contribute(db: Session, user_id: str, points: int) -> None:
    """Adds points to every active event: atomic SQL increment for the server total, per-player row upsert."""
    if points <= 0:
        return
    p = db.get(PlayerProfile, user_id)
    if p is None or p.is_ai:
        return  # AI personas never inflate real event progress
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
    for ev in active_events(db):
        db.execute(update(WorldEvent).where(WorldEvent.id == ev.id).values(progress=WorldEvent.progress + points)
                   .execution_options(synchronize_session=False))
        row = db.get(WorldEventContribution, (ev.id, user_id))
        if row is None:
            try:
                with db.begin_nested():
                    row = WorldEventContribution(event_id=ev.id, user_id=user_id, guild_id=m.guild_id if m else None, points=0)
                    db.add(row)
            except IntegrityError:
                row = db.get(WorldEventContribution, (ev.id, user_id))
        if row is not None:
            row.points = (row.points or 0) + points
            if m and not row.guild_id:
                row.guild_id = m.guild_id
    from .progression import add_stat
    add_stat(db, user_id, "event_points", points)


# ------------------------------------------------------------------ finish & consequences
def finish(db: Session, ev: WorldEvent) -> None:
    if ev.status != "active":
        return
    db.refresh(ev)
    tpl = E()["templates"][ev.template]
    success = ev.progress >= ev.goal
    ev.outcome = "success" if success else "failure"
    ev.status = "finished"
    choice = None
    if tpl.get("choices"):
        votes = {}
        for c in db.scalars(select(WorldEventContribution).where(WorldEventContribution.event_id == ev.id,
                                                                 WorldEventContribution.choice.is_not(None))):
            votes[c.choice] = votes.get(c.choice, 0) + int(c.points or 0)
        ev.choice_votes = votes
        choice = max(votes, key=votes.get) if votes else sorted(tpl["choices"])[0]
    res = tpl["success" if success else "failure"]

    def apply(st: dict):
        st.setdefault("regions", {}).update(res.get("region_status", {}))
        unl = list(res.get("unlock", [])) + list((res.get("unlock_by_choice") or {}).get(choice, []))
        st.setdefault("unlocked", [])
        st["unlocked"] += [u for u in unl if u not in st["unlocked"]]
        story = (res.get("story_by_choice") or {}).get(choice) or res.get("story")
        if story:
            st.setdefault("story", []).append({"event": ev.name, "text": story, "at": utcnow().isoformat()})
        st.setdefault("decor", [])
        st["decor"] += [d for d in res.get("decor", []) if d not in st["decor"]]
        st.setdefault("chronicle", []).append({"at": utcnow().isoformat(), "event": ev.name, "outcome": ev.outcome,
                                               "text": res.get("chronicle", ev.name), "choice": choice,
                                               "progress": ev.progress, "goal": ev.goal})
    change_world(db, f"Итог события «{ev.name}»: {ev.outcome}", apply)
    rw = tpl["rewards"]
    for c in db.scalars(select(WorldEventContribution).where(WorldEventContribution.event_id == ev.id,
                                                             WorldEventContribution.rewarded.is_(False)).with_for_update()):
        reward = dict(rw["participant"])
        bonus = min(rw["max_bonus_gold"], (int(c.points) // 1000) * rw["per_1000"]["gold"])
        reward["gold"] = reward.get("gold", 0) + bonus
        if success:
            for k, v in rw["success_bonus"].items():
                reward[k] = reward.get(k, 0) + v
            if "festival_ribbons" in res.get("decor", []):
                reward["cosmetic"] = "fortress_festival_ribbons"
        notify(db, c.user_id, f"Событие «{ev.name}» завершено",
               ("Победа сервера! " if success else "Цель не достигнута. ") + f"Ваш вклад: {c.points} очков.", reward)
        c.rewarded = True
        db.add(SeasonResult(user_id=c.user_id, category="event", season_id=0, ref=ev.code[:64],
                            result={"name": ev.name, "points": int(c.points), "outcome": ev.outcome}))
    from .chat import system_message
    system_message(db, "global", f"Событие «{ev.name}» завершено: " + ("успех!" if success else "неудача.") + " " + (res.get("story") or ""))
    db.flush()


def finish_due(db: Session) -> int:
    n = 0
    for ev in db.scalars(select(WorldEvent).where(WorldEvent.status == "active", WorldEvent.ends_at <= utcnow())).all():
        finish(db, ev)
        n += 1
    return n


# ------------------------------------------------------------------ API
def event_view(db: Session, ev: WorldEvent, user_id: str) -> dict:
    tpl = E()["templates"][ev.template]
    mine = db.get(WorldEventContribution, (ev.id, user_id))
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
    guild_pts = 0
    if m:
        guild_pts = db.scalar(select(func.coalesce(func.sum(WorldEventContribution.points), 0)).where(
            WorldEventContribution.event_id == ev.id, WorldEventContribution.guild_id == m.guild_id)) or 0
    top = db.scalars(select(WorldEventContribution).where(WorldEventContribution.event_id == ev.id)
                     .order_by(WorldEventContribution.points.desc()).limit(10)).all()
    gtop = db.execute(select(WorldEventContribution.guild_id, func.sum(WorldEventContribution.points)).where(
        WorldEventContribution.event_id == ev.id, WorldEventContribution.guild_id.is_not(None))
        .group_by(WorldEventContribution.guild_id).order_by(func.sum(WorldEventContribution.points).desc()).limit(5)).all()
    participants = db.scalar(select(func.count()).select_from(WorldEventContribution).where(WorldEventContribution.event_id == ev.id)) or 0
    sc = db.get(StatCounter, (user_id, f"evb:{day()}"))
    return {"id": ev.id, "name": ev.name, "kind": ev.kind, "scale": ev.scale, "desc": tpl["desc"], "status": ev.status,
            "starts_at": as_utc(ev.starts_at).isoformat(), "ends_at": as_utc(ev.ends_at).isoformat(),
            "goal": ev.goal, "progress": ev.progress, "outcome": ev.outcome, "participants": participants,
            "my_points": int(mine.points) if mine else 0, "my_choice": mine.choice if mine else None,
            "guild_points": int(guild_pts), "choices": tpl.get("choices"), "votes": ev.choice_votes,
            "top": [{"nickname": card(db, c.user_id)["nickname"], "points": int(c.points)} for c in top],
            "top_guilds": [{"name": db.get(Guild, gid).name if db.get(Guild, gid) else "?", "points": int(p)} for gid, p in gtop],
            "rewards": tpl["rewards"], "points_table": E()["points"],
            "battles_left": max(0, EVENT_BATTLES_PER_DAY - (sc.value if sc else 0)),
            "consequences": {"success": tpl["success"].get("story") or "Новая глава мира", "failure": tpl["failure"].get("story")}}


@router.get("")
def events(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    ensure(db)
    finish_due(db)
    db.commit()
    act = [event_view(db, e, user.id) for e in active_events(db)]
    past = [event_view(db, e, user.id) for e in db.scalars(select(WorldEvent).where(WorldEvent.status == "finished")
                                                          .order_by(WorldEvent.ends_at.desc()).limit(5))]
    ws = world(db)
    db.commit()
    return {"active": act, "past": past, "world": {"version": ws.version, **ws.state}}


class VoteIn(BaseModel):
    choice: str = Field(max_length=32)


@router.post("/{event_id}/vote")
def vote(event_id: str, body: VoteIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    ev = db.get(WorldEvent, event_id)
    if ev is None or ev.status != "active":
        raise GameError("not_found", "Событие не активно", 404)
    tpl = E()["templates"][ev.template]
    if not tpl.get("choices") or body.choice not in tpl["choices"]:
        raise GameError("bad_choice", "Нет такого варианта")
    row = db.get(WorldEventContribution, (ev.id, user.id))
    if row is None or row.points <= 0:
        raise GameError("no_contribution", "Голосовать могут участники события: сначала внесите вклад", 409)
    row.choice = body.choice
    db.commit()
    return {"choice": row.choice, "weight": int(row.points)}


@router.post("/{event_id}/battle")
def event_battle(event_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                 db: Session = Depends(get_db)):
    """Event battle against the invading army; scales with the player's progress. Points go to the event."""
    def do():
        ev = db.get(WorldEvent, event_id)
        if ev is None or ev.status != "active" or as_utc(ev.ends_at) <= utcnow():
            raise GameError("not_found", "Событие не активно", 404)
        k = f"evb:{day()}"
        sc = db.get(StatCounter, (user.id, k), with_for_update=True)
        if sc is None:
            sc = StatCounter(user_id=user.id, key=k, value=0)
            db.add(sc)
        if sc.value >= EVENT_BATTLES_PER_DAY:
            raise GameError("limit", "Бои события на сегодня закончились", 409)
        sc.value += 1
        p = db.get(PlayerProfile, user.id)
        tpl = E()["templates"][ev.template]
        lvl = max(3, p.level + int(tpl.get("enemy_level_add", 2)))
        codes = ["e_warrior", "e_rogue", "e_mage", "e_warrior", "e_minion"]
        enemies = []
        for slot, code in enumerate(codes):
            h = db.get(Hero, code)
            from ..game.battle_sim import hero_stats, make_unit
            enemies.append(make_unit(1, slot, hero_dict(h), hero_stats(hero_dict(h), lvl), lvl, FACTION_ADV.get(h.faction_code)))
        spec = freeze_squad(db, user.id)
        sim, _ = run_battle(units_from_spec(db, spec, 0), enemies, secrets.randbits(48))
        won = sim["result"] == "victory"
        pts = E()["points"]["battle_win"] * 3 if won else E()["points"]["battle"]
        contribute(db, user.id, pts)
        reward = give(db, user.id, {"gold": 1500 if won else 400}, "event_battle", ev.id)
        return {"simulation": sim, "points": pts, "won": won, "reward": reward, "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, f"event_battle:{event_id}", {}, do)


@router.get("/world")
def world_view(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    ws = world(db)
    db.commit()
    return {"version": ws.version, **ws.state}


_ = CampaignNode
