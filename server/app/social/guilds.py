"""Guilds: management (6 roles, permissions, applications, invites, log), development (buildings, research,
specialization branches), activities (daily tasks, donations, expeditions, wars) and fair weekly rewards."""
from __future__ import annotations

import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import (
    ArenaProfile, Guild, GuildApplication, GuildContribution, GuildExpedition, GuildLog, GuildMember, GuildTask,
    GuildUpgrade, GuildWar, GuildWarAttack, PlayerProfile,
)
from ..services import spend, wallet_dict
from . import progression as P
from .common import card, cfg, day, freeze_squad, give, notify, profile, pvp, squad_power, summary

router = APIRouter(prefix="/guilds", tags=["guilds"])


def G() -> dict:
    return cfg()["guilds"]


ROLES = ["leader", "deputy", "officer", "veteran", "member", "novice"]


def rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else len(ROLES)


def can(role: str, perm: str) -> bool:
    return perm in G()["permissions"].get(role, [])


# ------------------------------------------------------------------ helpers
def membership(db: Session, user_id: str) -> GuildMember | None:
    return db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))


def my_guild(db: Session, user_id: str, perm: str | None = None, lock: bool = False) -> tuple[Guild, GuildMember]:
    m = membership(db, user_id)
    if m is None:
        raise GameError("no_guild", "Вы не состоите в гильдии", 404)
    g = db.get(Guild, m.guild_id, with_for_update=lock)
    if perm and not can(m.role, perm):
        raise GameError("forbidden", "Недостаточно прав для этого действия", 403)
    return g, m


def members(db: Session, guild_id: str) -> list[GuildMember]:
    return list(db.scalars(select(GuildMember).where(GuildMember.guild_id == guild_id)))


def member_count(db: Session, guild_id: str) -> int:
    return db.scalar(select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == guild_id)) or 0


def log(db: Session, guild_id: str, actor: str | None, action: str, target: str | None = None, **payload) -> None:
    db.add(GuildLog(guild_id=guild_id, actor_id=actor, action=action, target_id=target, payload=payload))


def levels(db: Session, guild_id: str) -> dict[str, int]:
    return {u.code: u.level for u in db.scalars(select(GuildUpgrade).where(GuildUpgrade.guild_id == guild_id))}


GUILD_SETTINGS_DEFAULT = {"min_power": 0, "auto_accept": False, "notify_chat": True}
EMBLEMS = ["wolf", "bear", "eagle", "tree", "horse", "stone"]


def gsettings(g: Guild) -> dict:
    return {**GUILD_SETTINGS_DEFAULT, **(g.settings or {})}


def public_id(g: Guild) -> str:
    return "G-" + str(int(g.id.replace("-", "")[:8], 16) % 10000).zfill(4)


def guild_power(db: Session, guild_id: str) -> int:
    from .common import compute_power
    return sum(compute_power(db, m.user_id) for m in members(db, guild_id))


def guild_rank(db: Session, g: Guild) -> int:
    return (db.scalar(select(func.count()).select_from(Guild).where(
        Guild.is_ai.is_(False) if not g.is_ai else Guild.is_ai.is_(True),
        (Guild.level > g.level) | ((Guild.level == g.level) & (Guild.exp > g.exp)))) or 0) + 1


def guild_level(exp: int) -> int:
    lv = 1
    for i, need in enumerate(G()["level_exp"]):
        if exp >= need:
            lv = i + 1
    return lv


def add_points(db: Session, g: Guild, m: GuildMember, points: int, kind: str, exp: int = 0) -> None:
    m.contribution_week = (m.contribution_week or 0) + points
    m.contribution_total = (m.contribution_total or 0) + points
    m.last_active_at = utcnow()
    g.week_points = (g.week_points or 0) + points
    g.exp = (g.exp or 0) + exp
    g.level = guild_level(g.exp)
    db.add(GuildContribution(guild_id=g.id, user_id=m.user_id, kind=kind, amount=points))


def guild_bonuses(db: Session, user_id: str) -> dict[str, float]:
    """Guild buildings, research and specialization bonuses for the member (PvE / bosses / wars only)."""
    m = membership(db, user_id)
    out: dict[str, float] = {}
    if m is None:
        return out
    g = db.get(Guild, m.guild_id)
    lv = levels(db, g.id)

    def add(bonus: dict, n: int):
        for k, v in bonus.items():
            out[k] = out.get(k, 0) + float(v) * n

    for code, b in G()["buildings"].items():
        if b.get("bonus") and lv.get(code, 0) > 0:
            add(b["bonus"], lv[code])
    for code, r in G()["research"].items():
        if r.get("bonus") and lv.get(code, 0) > 0 and (r.get("branch") in (None, g.specialization)):
            add(r["bonus"], lv[code])
    if g.specialization in G()["specializations"]:
        add(G()["specializations"][g.specialization]["bonus"], 1)
    return out


def join(db: Session, g: Guild, user_id: str, actor: str | None, how: str) -> GuildMember:
    if membership(db, user_id):
        raise GameError("already_in_guild", "Игрок уже состоит в гильдии", 409)
    if member_count(db, g.id) >= G()["max_members"]:
        raise GameError("guild_full", f"В гильдии максимум {G()['max_members']} участников", 409)
    m = GuildMember(guild_id=g.id, user_id=user_id, role="novice", last_active_at=utcnow())
    db.add(m)
    db.flush()
    for a in db.scalars(select(GuildApplication).where(GuildApplication.user_id == user_id,
                                                       GuildApplication.status == "pending")):
        a.status = "cancelled"
    log(db, g.id, actor, "join", user_id, how=how)
    P.add_stat(db, user_id, "guild_joined", absolute=1)
    if gsettings(g).get("notify_chat", True):
        from .chat import system_message
        system_message(db, f"guild:{g.id}", f"{profile(db, user_id).nickname} вступает в гильдию.")
    return m


def task_progress(db: Session, user_id: str, code: str, n: int = 1) -> None:
    m = membership(db, user_id)
    if m is None:
        return
    t = next((x for x in G()["daily_tasks"] if x["code"] == code), None)
    if t is None:
        return
    d = day()
    gt = db.get(GuildTask, (user_id, d, code))
    if gt is None:
        gt = GuildTask(user_id=user_id, day=d, code=code, guild_id=m.guild_id, progress=0)
        db.add(gt)
    gt.progress = min(t["target"], (gt.progress or 0) + n)
    m.last_active_at = utcnow()
    db.flush()


# ------------------------------------------------------------------ views
def guild_brief(db: Session, g: Guild) -> dict:
    return {"id": g.id, "name": g.name, "tag": g.tag, "level": g.level, "emblem": g.emblem, "is_ai": g.is_ai,
            "members": member_count(db, g.id), "max_members": G()["max_members"], "join_mode": g.join_mode,
            "min_level": g.min_level, "description": g.description, "week_points": g.week_points or 0,
            "specialization": g.specialization}


def _expedition_view(e: GuildExpedition) -> dict:
    c = G()["expeditions"].get(e.code, {})
    return {"id": e.id, "code": e.code, "name": c.get("name", e.code), "status": e.status,
            "participants": len(e.participants or []), "power": sum(int(p.get("power", 0)) for p in e.participants or []),
            "power_goal": c.get("power_goal"), "ends_at": as_utc(e.ends_at).isoformat(), "result": e.result,
            "joined_ids": [p["user_id"] for p in e.participants or []]}


@router.get("/mine")
def mine(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    m = membership(db, user.id)
    invites = [{"id": a.id, "guild": guild_brief(db, db.get(Guild, a.guild_id))} for a in db.scalars(
        select(GuildApplication).where(GuildApplication.user_id == user.id, GuildApplication.kind == "invite",
                                       GuildApplication.status == "pending"))]
    if m is None:
        return {"guild": None, "invites": invites}
    settle_expeditions(db, m.guild_id)
    g = db.get(Guild, m.guild_id)
    now = utcnow()
    mem = []
    for x in members(db, g.id):
        c = card(db, x.user_id, user.id)
        inactive = (now - as_utc(x.last_active_at)).days if x.last_active_at else 0
        mem.append({**c, "role": x.role, "role_name": G()["role_names"][x.role], "week": x.contribution_week or 0,
                    "total": x.contribution_total or 0, "inactive_days": inactive,
                    "warned": x.warned_at is not None, "joined_at": as_utc(x.joined_at).isoformat()})
    mem.sort(key=lambda r: (rank(r["role"]), -r["week"]))
    lv = levels(db, g.id)
    d = day()
    tasks = []
    for t in G()["daily_tasks"]:
        gt = db.get(GuildTask, (user.id, d, t["code"]))
        tasks.append({**t, "progress": gt.progress if gt else 0, "claimed": bool(gt and gt.claimed)})
    apps = []
    if can(m.role, "accept"):
        apps = [{"id": a.id, "player": card(db, a.user_id, user.id), "at": as_utc(a.created_at).isoformat()}
                for a in db.scalars(select(GuildApplication).where(GuildApplication.guild_id == g.id,
                                                                   GuildApplication.kind == "application",
                                                                   GuildApplication.status == "pending"))]
    logs = [{"at": as_utc(lg.created_at).isoformat(), "action": lg.action,
             "actor": profile(db, lg.actor_id).nickname if lg.actor_id and db.get(PlayerProfile, lg.actor_id) else "Система",
             "target": profile(db, lg.target_id).nickname if lg.target_id and db.get(PlayerProfile, lg.target_id) else None,
             "payload": lg.payload} for lg in db.scalars(select(GuildLog).where(GuildLog.guild_id == g.id)
                                                         .order_by(GuildLog.id.desc()).limit(40))]
    exps = [_expedition_view(e) for e in db.scalars(select(GuildExpedition).where(GuildExpedition.guild_id == g.id)
                                                    .order_by(GuildExpedition.started_at.desc()).limit(6))]
    war = db.scalar(select(GuildWar).where(or_(GuildWar.guild_a == g.id, GuildWar.guild_b == g.id))
                    .order_by(GuildWar.starts_at.desc()))
    lv_next = G()["level_exp"][g.level] if g.level < len(G()["level_exp"]) else None
    return {
        "guild": {**guild_brief(db, g), "exp": g.exp or 0, "exp_next": lv_next, "treasury": g.treasury or 0,
                  "public_id": public_id(g), "power": guild_power(db, g.id), "rank": guild_rank(db, g),
                  "settings": gsettings(g), "emblems": EMBLEMS},
        "my_role": m.role, "my_role_name": G()["role_names"][m.role],
        "permissions": G()["permissions"][m.role], "role_names": G()["role_names"], "members": mem,
        "buildings": [{"code": c, **{k: v for k, v in b.items() if k != "cost"}, "level": lv.get(c, 1 if c == "hall" else 0),
                       "next_cost": b["cost"][lv.get(c, 1 if c == "hall" else 0)] if lv.get(c, 1 if c == "hall" else 0) < b["max"] else None}
                      for c, b in G()["buildings"].items()],
        "research": [{"code": c, **{k: v for k, v in r.items() if k != "cost"}, "level": lv.get(c, 0),
                      "active": r.get("branch") in (None, g.specialization),
                      "next_cost": r["cost"][lv.get(c, 0)] if lv.get(c, 0) < r["max"] else None}
                     for c, r in G()["research"].items()],
        "specializations": G()["specializations"], "bonuses": guild_bonuses(db, user.id),
        "tasks": tasks, "applications": apps, "log": logs, "expeditions": exps,
        "expedition_types": G()["expeditions"], "war": war_view(db, war, g.id) if war else None,
        "donate": G()["donate"]["gold"], "donated_today": _donated_today(db, user.id),
        "invites": invites, "week_rewards": G()["week_rewards"],
        "ai_policy": _ai_policy_view(g),
    }


def _ai_policy_view(g: Guild) -> dict:
    from .ai.control import GUILD_NAMES, guild_policy
    return {"values": guild_policy(g), "names": GUILD_NAMES}


@router.get("/list")
def guild_list(q: str = Query("", max_length=32), offset: int = Query(0, ge=0, le=1000),
               user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    stmt = select(Guild)
    if q.strip():
        like = "%" + q.strip().replace("%", "") + "%"
        stmt = stmt.where(or_(Guild.name.ilike(like), Guild.tag.ilike(like)))
    rows = db.scalars(stmt.order_by(Guild.is_ai, Guild.level.desc(), Guild.week_points.desc()).offset(offset).limit(20)).all()
    applied = set(db.scalars(select(GuildApplication.guild_id).where(GuildApplication.user_id == user.id,
                                                                     GuildApplication.status == "pending")))
    return {"items": [{**guild_brief(db, g), "applied": g.id in applied} for g in rows],
            "offset": offset, "next": offset + 20 if len(rows) == 20 else None,
            "create_cost": G()["create_cost"], "create_min_level": G()["create_min_level"]}


@router.get("/{guild_id}/view")
def guild_view(guild_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g = db.get(Guild, guild_id)
    if g is None:
        raise GameError("not_found", "Гильдия не найдена", 404)
    mem = [{**card(db, x.user_id, user.id), "role": x.role, "role_name": G()["role_names"][x.role]}
           for x in members(db, g.id)]
    mem.sort(key=lambda r: rank(r["role"]))
    return {"guild": guild_brief(db, g), "members": mem, "buildings": levels(db, g.id)}


# ------------------------------------------------------------------ create / join / leave
NAME_RE = re.compile(r"^[\w \-'ёЁ]{3,24}$")


class CreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=24)
    tag: str = Field(min_length=2, max_length=5)
    description: str = Field(default="", max_length=300)
    join_mode: str = Field(default="open", pattern="^(open|approval|invite)$")
    min_level: int = Field(default=1, ge=1, le=80)
    emblem: str = Field(default="stone", max_length=32)


def _check_text(*texts: str) -> None:
    from .chat import contains_bad
    for t in texts:
        if contains_bad(t):
            raise GameError("bad_text", "Текст не прошёл фильтр")


@router.post("/create")
def create(body: CreateIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
           db: Session = Depends(get_db)):
    name, tag = body.name.strip(), body.tag.strip().upper()
    if not NAME_RE.match(name) or not re.match(r"^[\wЁё]{2,5}$", tag):
        raise GameError("bad_name", "Название: 3–24 буквы, цифры, пробел, дефис; тег: 2–5 символов")
    _check_text(name, tag, body.description)

    def do():
        if membership(db, user.id):
            raise GameError("already_in_guild", "Сначала покиньте текущую гильдию", 409)
        if profile(db, user.id).level < G()["create_min_level"]:
            raise GameError("level", f"Создать гильдию можно с {G()['create_min_level']} уровня", 403)
        if db.scalar(select(Guild).where(func.lower(Guild.name) == name.lower())):
            raise GameError("name_taken", "Такое название уже занято", 409)
        spend(db, user.id, G()["create_cost"], "guild_create")
        g = Guild(name=name, tag=tag, description=body.description.strip(), join_mode=body.join_mode,
                  min_level=body.min_level, emblem=body.emblem, leader_id=user.id)
        db.add(g)
        db.flush()
        db.add(GuildUpgrade(guild_id=g.id, code="hall", kind="building", level=1))
        m = join(db, g, user.id, user.id, "create")
        m.role = "leader"
        log(db, g.id, user.id, "create")
        audit(db, user.id, "guild.create", guild=g.id, name=name)
        return {"guild_id": g.id, "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, "guild_create", body.model_dump(), do)


@router.post("/{guild_id}/join")
def request_join(guild_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g = db.get(Guild, guild_id, with_for_update=True)
    if g is None:
        raise GameError("not_found", "Гильдия не найдена", 404)
    if membership(db, user.id):
        raise GameError("already_in_guild", "Вы уже в гильдии", 409)
    if profile(db, user.id).level < (g.min_level or 1):
        raise GameError("level", f"Нужен уровень {g.min_level}", 403)
    gs = gsettings(g)
    from .common import compute_power
    if gs["min_power"] and compute_power(db, user.id) < int(gs["min_power"]):
        raise GameError("power", f"Нужна сила отряда от {int(gs['min_power']):,}".replace(",", " "), 403)
    if g.join_mode == "open" or (g.join_mode == "approval" and gs["auto_accept"]):
        join(db, g, user.id, user.id, "open")
        db.commit()
        return {"status": "joined"}
    if g.join_mode == "invite":
        raise GameError("invite_only", "Вступление только по приглашению", 403)
    if db.scalar(select(GuildApplication).where(GuildApplication.guild_id == g.id, GuildApplication.user_id == user.id,
                                                GuildApplication.status == "pending")):
        return {"status": "pending"}
    a = GuildApplication(guild_id=g.id, user_id=user.id, kind="application")
    db.add(a)
    db.flush()
    if g.is_ai:  # virtual guild leaders decide quickly
        from .ai.population import ai_guild_review
        if ai_guild_review(db, g, user.id):
            a.status = "accepted"
            join(db, g, user.id, g.leader_id, "approval")
            db.commit()
            return {"status": "joined"}
    log(db, g.id, user.id, "apply")
    db.commit()
    return {"status": "pending", "application_id": a.id}


@router.post("/applications/{app_id}/{action}")
def application(app_id: str, action: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    a = db.get(GuildApplication, app_id, with_for_update=True)
    if a is None or a.status != "pending":
        raise GameError("not_found", "Заявка не найдена", 404)
    if a.kind == "invite":
        if a.user_id != user.id:
            raise GameError("forbidden", "Это не ваше приглашение", 403)
        g = db.get(Guild, a.guild_id, with_for_update=True)
        if action == "accept":
            a.status = "accepted"
            join(db, g, user.id, a.invited_by, "invite")
        else:
            a.status = "declined"
    else:
        g, m = my_guild(db, user.id, "accept", lock=True)
        if g.id != a.guild_id:
            raise GameError("forbidden", "Заявка в другую гильдию", 403)
        if action == "accept":
            a.status = "accepted"
            join(db, g, a.user_id, user.id, "approval")
        else:
            a.status = "declined"
            log(db, g.id, user.id, "decline", a.user_id)
    db.commit()
    return {"status": a.status}


class TargetIn(BaseModel):
    user_id: str = Field(max_length=36)


@router.post("/invite")
def invite(body: TargetIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "invite")
    profile(db, body.user_id)
    if membership(db, body.user_id):
        raise GameError("already_in_guild", "Игрок уже в гильдии", 409)
    if db.scalar(select(GuildApplication).where(GuildApplication.guild_id == g.id, GuildApplication.user_id == body.user_id,
                                                GuildApplication.status == "pending", GuildApplication.kind == "invite")):
        return {"status": "pending"}
    tp = profile(db, body.user_id)
    a = GuildApplication(guild_id=g.id, user_id=body.user_id, kind="invite", invited_by=user.id)
    db.add(a)
    log(db, g.id, user.id, "invite", body.user_id)
    db.flush()
    if tp.is_ai:
        from .ai.population import ai_accept_guild_invite
        if ai_accept_guild_invite(db, body.user_id, g):
            a.status = "accepted"
            join(db, g, body.user_id, user.id, "invite")
    db.commit()
    return {"status": a.status}


@router.post("/leave")
def leave(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, lock=True)
    n = member_count(db, g.id)
    if m.role == "leader" and n > 1:
        raise GameError("leader_must_transfer", "Сначала передайте руководство другому участнику", 409)
    db.delete(m)
    log(db, g.id, user.id, "leave")
    if gsettings(g).get("notify_chat", True) and n > 1:
        from .chat import system_message
        system_message(db, f"guild:{g.id}", f"{profile(db, user.id).nickname} покидает гильдию.")
    if n == 1:
        db.flush()
        db.delete(g)
    db.commit()
    return {"ok": True}


class RoleIn(BaseModel):
    role: str = Field(pattern="^(deputy|officer|veteran|member|novice)$")


@router.post("/members/{target_id}/role")
def set_role(target_id: str, body: RoleIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "promote", lock=True)
    t = db.get(GuildMember, (g.id, target_id))
    if t is None:
        raise GameError("not_found", "Участник не найден", 404)
    if rank(t.role) <= rank(m.role) or rank(body.role) <= rank(m.role):
        raise GameError("forbidden", "Можно менять должность только младших и не выше своей", 403)
    old, t.role = t.role, body.role
    log(db, g.id, user.id, "role", target_id, old=old, new=body.role)
    db.commit()
    return {"role": t.role}


@router.post("/members/{target_id}/kick")
def kick(target_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "kick", lock=True)
    t = db.get(GuildMember, (g.id, target_id))
    if t is None:
        raise GameError("not_found", "Участник не найден", 404)
    if rank(t.role) <= rank(m.role):
        raise GameError("forbidden", "Нельзя исключить участника своей или старшей должности", 403)
    db.delete(t)
    log(db, g.id, user.id, "kick", target_id)
    notify(db, target_id, "Вы исключены из гильдии", f"Руководство гильдии «{g.name}» исключило вас.")
    db.commit()
    return {"ok": True}


@router.post("/members/{target_id}/warn")
def warn(target_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "warn")
    t = db.get(GuildMember, (g.id, target_id))
    if t is None or rank(t.role) <= rank(m.role):
        raise GameError("forbidden", "Нельзя предупредить этого участника", 403)
    t.warned_at = utcnow()
    log(db, g.id, user.id, "warn", target_id)
    notify(db, target_id, "Предупреждение гильдии", f"Руководство гильдии «{g.name}» просит вас проявить активность.")
    db.commit()
    return {"ok": True}


@router.post("/transfer")
def transfer(body: TargetIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "transfer", lock=True)
    t = db.get(GuildMember, (g.id, body.user_id))
    if t is None or t.user_id == user.id:
        raise GameError("not_found", "Участник не найден", 404)
    t.role, m.role, g.leader_id = "leader", "deputy", t.user_id
    log(db, g.id, user.id, "transfer", t.user_id)
    db.commit()
    return {"ok": True}


class EditIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=24)
    description: str | None = Field(default=None, max_length=300)
    join_mode: str | None = Field(default=None, pattern="^(open|approval|invite)$")
    min_level: int | None = Field(default=None, ge=1, le=80)
    emblem: str | None = Field(default=None, max_length=32)
    min_power: int | None = Field(default=None, ge=0, le=10_000_000)
    auto_accept: bool | None = None
    notify_chat: bool | None = None


@router.post("/edit")
def edit(body: EditIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "edit", lock=True)
    if body.name is not None and body.name.strip() != g.name:
        name = body.name.strip()
        if m.role != "leader":
            raise GameError("forbidden", "Название меняет только глава", 403)
        if not NAME_RE.match(name):
            raise GameError("bad_name", "Название: 3–24 буквы, цифры, пробел, дефис")
        _check_text(name)
        if db.scalar(select(Guild).where(func.lower(Guild.name) == name.lower(), Guild.id != g.id)):
            raise GameError("name_taken", "Такое название уже занято", 409)
        g.name = name
    if body.description is not None:
        _check_text(body.description)
        g.description = body.description.strip()
    if body.emblem is not None and body.emblem not in EMBLEMS:
        raise GameError("bad_emblem", "Нет такого знамени")
    for f in ("join_mode", "min_level", "emblem"):
        if getattr(body, f) is not None:
            setattr(g, f, getattr(body, f))
    st = gsettings(g)
    for f in ("min_power", "auto_accept", "notify_chat"):
        if getattr(body, f) is not None:
            st[f] = getattr(body, f)
    g.settings = st
    log(db, g.id, user.id, "edit")
    db.commit()
    return guild_brief(db, g)


# ------------------------------------------------------------------ development
def _donated_today(db: Session, user_id: str) -> int:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(GuildContribution).where(
        GuildContribution.user_id == user_id, GuildContribution.kind == "donate",
        GuildContribution.created_at >= start)) or 0


@router.post("/donate")
def donate(user: CurrentUser = Depends(player), key: str = Depends(require_key), db: Session = Depends(get_db)):
    def do():
        g, m = my_guild(db, user.id, lock=True)
        d = G()["donate"]["gold"]
        if _donated_today(db, user.id) >= d["daily_max"]:
            raise GameError("limit", "Сегодня вы уже сделали максимум пожертвований", 409)
        spend(db, user.id, {"gold": d["per"]}, "guild_donate", g.id)
        g.treasury = (g.treasury or 0) + d["treasury"]
        add_points(db, g, m, d["points"], "donate", d["exp"])
        P.on(db, user.id, "guild_donate")
        return {"treasury": g.treasury, "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, "guild_donate", {}, do)


def _upgrade(db: Session, g: Guild, code: str, kind: str, conf: dict, actor: str) -> int:
    lv = levels(db, g.id)
    cur = lv.get(code, 1 if code == "hall" else 0)
    if cur >= conf["max"]:
        raise GameError("max_level", "Достигнут максимальный уровень", 409)
    for req, need in (conf.get("requires") or {}).items():
        if lv.get(req, 1 if req == "hall" else 0) < need:
            raise GameError("requires", f"Нужен «{G()['buildings'][req]['name']}» уровня {need}", 409)
    if kind == "research" and conf.get("branch") and conf["branch"] != g.specialization:
        raise GameError("branch", "Исследование доступно только выбранной специализации", 409)
    if kind == "research" and lv.get("hall", 1) < 2:
        raise GameError("requires", "Исследования открываются с Зала Совета 2 уровня", 409)
    cost = conf["cost"][cur]
    if (g.treasury or 0) < cost:
        raise GameError("not_enough_treasury", "Не хватает ресурсов в казне", 409)
    g.treasury -= cost
    row = db.get(GuildUpgrade, (g.id, code))
    if row is None:
        row = GuildUpgrade(guild_id=g.id, code=code, kind=kind, level=cur)
        db.add(row)
    row.level = cur + 1
    log(db, g.id, actor, kind, None, code=code, level=row.level, cost=cost)
    return row.level


@router.post("/build/{code}")
def build(code: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "build", lock=True)
    conf = G()["buildings"].get(code)
    if conf is None:
        raise GameError("not_found", "Нет такой постройки", 404)
    lv = _upgrade(db, g, code, "building", conf, user.id)
    db.commit()
    return {"code": code, "level": lv, "treasury": g.treasury}


@router.post("/research/{code}")
def research(code: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "research", lock=True)
    conf = G()["research"].get(code)
    if conf is None:
        raise GameError("not_found", "Нет такого исследования", 404)
    lv = _upgrade(db, g, code, "research", conf, user.id)
    db.commit()
    return {"code": code, "level": lv, "treasury": g.treasury}


class SpecIn(BaseModel):
    code: str = Field(max_length=32)


@router.post("/specialize")
def specialize(body: SpecIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "specialize", lock=True)
    if body.code not in G()["specializations"]:
        raise GameError("not_found", "Нет такой специализации", 404)
    if g.specialization == body.code:
        return {"specialization": g.specialization}
    if g.specialization:  # changing the path costs treasury; branch research is kept but inactive
        if (g.treasury or 0) < 3000:
            raise GameError("not_enough_treasury", "Смена пути стоит 3000 ресурсов казны", 409)
        g.treasury -= 3000
    g.specialization = body.code
    log(db, g.id, user.id, "specialize", None, code=body.code)
    db.commit()
    return {"specialization": g.specialization}


# ------------------------------------------------------------------ daily tasks
@router.post("/tasks/{code}/claim")
def task_claim(code: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
               db: Session = Depends(get_db)):
    t = next((x for x in G()["daily_tasks"] if x["code"] == code), None)
    if t is None:
        raise GameError("not_found", "Нет такого задания", 404)

    def do():
        g, m = my_guild(db, user.id, lock=True)
        gt = db.get(GuildTask, (user.id, day(), code), with_for_update=True)
        if gt is None or gt.progress < t["target"]:
            raise GameError("not_done", "Задание ещё не выполнено", 409)
        if gt.claimed:
            raise GameError("already_claimed", "Награда уже получена", 409)
        gt.claimed = True
        add_points(db, g, m, t["points"], "task", t["points"])
        give(db, user.id, t["reward"], "guild_task", code)
        P.on(db, user.id, "guild_task", ref=code)
        return {"reward": t["reward"], "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, f"guild_task:{code}", {}, do)


# ------------------------------------------------------------------ expeditions
class ExpIn(BaseModel):
    code: str = Field(max_length=32)


@router.post("/expeditions/start")
def expedition_start(body: ExpIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "expedition", lock=True)
    c = G()["expeditions"].get(body.code)
    if c is None:
        raise GameError("not_found", "Нет такой экспедиции", 404)
    if db.scalar(select(GuildExpedition).where(GuildExpedition.guild_id == g.id, GuildExpedition.status == "active")):
        raise GameError("busy", "Экспедиция уже в пути", 409)
    e = GuildExpedition(guild_id=g.id, code=body.code, participants=[], ends_at=utcnow() + timedelta(hours=c["hours"]))
    db.add(e)
    db.flush()
    _join_exp(db, e, user.id)
    log(db, g.id, user.id, "expedition", None, code=body.code)
    db.commit()
    return _expedition_view(e)


def _exp_capacity(db: Session, g: Guild, c: dict) -> int:
    lv = levels(db, g.id)
    return int(c["max_participants"]) + lv.get("r_logistics", 0)


def _join_exp(db: Session, e: GuildExpedition, user_id: str) -> None:
    c = G()["expeditions"][e.code]
    parts = list(e.participants or [])
    if any(p["user_id"] == user_id for p in parts):
        raise GameError("already_joined", "Вы уже в экспедиции", 409)
    if len(parts) >= _exp_capacity(db, db.get(Guild, e.guild_id), c):
        raise GameError("full", "Мест в экспедиции нет", 409)
    pw = squad_power(freeze_squad(db, user_id))
    parts.append({"user_id": user_id, "power": pw})
    e.participants = parts


@router.post("/expeditions/{exp_id}/join")
def expedition_join(exp_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id)
    e = db.get(GuildExpedition, exp_id, with_for_update=True)
    if e is None or e.guild_id != g.id or e.status != "active" or as_utc(e.ends_at) <= utcnow():
        raise GameError("not_found", "Экспедиция недоступна", 404)
    _join_exp(db, e, user.id)
    m.last_active_at = utcnow()
    db.commit()
    return _expedition_view(e)


def settle_expeditions(db: Session, guild_id: str | None = None) -> int:
    """Resolves finished expeditions: success if the joined power reaches the goal, otherwise a partial reward."""
    stmt = select(GuildExpedition).where(GuildExpedition.status == "active", GuildExpedition.ends_at <= utcnow())
    if guild_id:
        stmt = stmt.where(GuildExpedition.guild_id == guild_id)
    n = 0
    for e in db.scalars(stmt.with_for_update(skip_locked=True)).all():
        c = G()["expeditions"][e.code]
        g = db.get(Guild, e.guild_id)
        parts = e.participants or []
        power = sum(int(p["power"]) for p in parts)
        enough = len(parts) >= c["min_participants"]
        ratio = min(1.0, power / c["power_goal"]) if enough else 0.25
        bonus = 1 + guild_bonuses_for_guild(db, g).get("expedition_pct", 0)
        reward = {k: int(v * ratio * bonus) for k, v in c["reward"].items()}
        g.treasury = (g.treasury or 0) + int(c["treasury"] * ratio)
        for p in parts:
            notify(db, p["user_id"], f"Экспедиция «{c['name']}» вернулась",
                   "Успех! Цель достигнута." if ratio >= 1 else f"Экспедиция выполнила цель на {int(ratio * 100)}%.", reward)
            m = db.get(GuildMember, (g.id, p["user_id"]))
            if m:
                add_points(db, g, m, 10, "expedition", 10)
        e.status = "done"
        e.result = {"ratio": round(ratio, 3), "power": power, "reward": reward, "success": ratio >= 1}
        log(db, g.id, None, "expedition_done", None, code=e.code, success=ratio >= 1)
        n += 1
    db.flush()
    return n


def guild_bonuses_for_guild(db: Session, g: Guild) -> dict:
    if g.leader_id and membership(db, g.leader_id):
        return guild_bonuses(db, g.leader_id)
    return {}


# ------------------------------------------------------------------ wars
def war_view(db: Session, w: GuildWar, my_guild_id: str) -> dict:
    other = w.guild_b if w.guild_a == my_guild_id else w.guild_a
    og = db.get(Guild, other)
    mine_score = w.score_a if w.guild_a == my_guild_id else w.score_b
    their = w.score_b if w.guild_a == my_guild_id else w.score_a
    targets = []
    if w.status == "active" and og:
        for x in members(db, og.id):
            ap = db.get(ArenaProfile, x.user_id)
            c = card(db, x.user_id)
            beaten = db.scalar(select(func.count()).select_from(GuildWarAttack).where(
                GuildWarAttack.war_id == w.id, GuildWarAttack.target_user_id == x.user_id, GuildWarAttack.result == "victory")) or 0
            targets.append({"user_id": x.user_id, "nickname": c["nickname"], "is_ai": c["is_ai"],
                            "power": ap.defense_power if ap and ap.defense else c["power"], "defeated_times": beaten})
    return {"id": w.id, "status": w.status, "opponent": guild_brief(db, og) if og else None, "score": mine_score,
            "opponent_score": their, "ends_at": as_utc(w.ends_at).isoformat(), "targets": targets,
            "winner": "mine" if w.winner == my_guild_id else ("opponent" if w.winner else None),
            "attacks_per_member": G()["war"]["attacks_per_member"]}


@router.post("/war/start")
def war_start(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "war", lock=True)
    if member_count(db, g.id) < G()["war"]["min_members"]:
        raise GameError("too_small", f"Для войны нужно минимум {G()['war']['min_members']} участника", 409)
    busy = set()
    for w in db.scalars(select(GuildWar).where(GuildWar.status == "active")):
        busy |= {w.guild_a, w.guild_b}
    if g.id in busy:
        raise GameError("busy", "Гильдия уже воюет", 409)
    cands = [x for x in db.scalars(select(Guild).where(Guild.id != g.id)) if x.id not in busy
             and member_count(db, x.id) >= G()["war"]["min_members"]]
    if not cands:
        raise GameError("no_opponent", "Сейчас нет свободного соперника, попробуйте позже", 409)
    cands.sort(key=lambda x: (abs((x.level or 1) - (g.level or 1)), x.is_ai, secrets.randbelow(100)))
    og = cands[0]
    w = GuildWar(guild_a=g.id, guild_b=og.id, ends_at=utcnow() + timedelta(hours=G()["war"]["hours"]))
    db.add(w)
    log(db, g.id, user.id, "war_start", None, opponent=og.name)
    log(db, og.id, None, "war_declared", None, opponent=g.name)
    db.commit()
    return war_view(db, w, g.id)


def defense_spec(db: Session, user_id: str) -> list[dict]:
    ap = db.get(ArenaProfile, user_id)
    if ap and ap.defense:
        return ap.defense
    return freeze_squad(db, user_id)


def do_war_attack(db: Session, attacker_id: str, target_id: str) -> dict:
    """One war attack (players via API, AI members via the AI engine). Raises GameError when not allowed."""
    g, m = my_guild(db, attacker_id)
    w = db.scalar(select(GuildWar).where(GuildWar.status == "active", or_(GuildWar.guild_a == g.id, GuildWar.guild_b == g.id))
                  .with_for_update())
    if w is None or as_utc(w.ends_at) <= utcnow():
        raise GameError("no_war", "Активной войны нет", 404)
    other = w.guild_b if w.guild_a == g.id else w.guild_a
    if db.get(GuildMember, (other, target_id)) is None:
        raise GameError("bad_target", "Цель не состоит в гильдии противника", 400)
    used = db.scalar(select(func.count()).select_from(GuildWarAttack).where(
        GuildWarAttack.war_id == w.id, GuildWarAttack.user_id == attacker_id)) or 0
    if used >= G()["war"]["attacks_per_member"]:
        raise GameError("limit", "Вы использовали все атаки этой войны", 409)
    mine = guild_bonuses(db, attacker_id)
    their = guild_bonuses(db, target_id)
    att = freeze_squad(db, attacker_id, extra={"atk_pct": mine.get("war_atk_pct", 0)})
    dfn = [dict(u, stats={**u["stats"], "hp": int(u["stats"]["hp"] * (1 + their.get("war_def_pct", 0)))})
           for u in defense_spec(db, target_id)]
    seed = secrets.randbits(48)
    sim = pvp(db, att, dfn, seed)
    pts = G()["war"]["win_points"] if sim["result"] == "victory" else G()["war"]["loss_points"]
    if w.guild_a == g.id:
        w.score_a += pts
    else:
        w.score_b += pts
    db.add(GuildWarAttack(war_id=w.id, user_id=attacker_id, guild_id=g.id, target_user_id=target_id,
                          result=sim["result"], points=pts, seed=seed))
    add_points(db, g, m, 5, "war", 5)
    return {"simulation": sim, "points": pts, "summary": summary(sim)}


@router.post("/war/attack")
def war_attack(body: TargetIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
               db: Session = Depends(get_db)):
    return run_idempotent(db, user.id, key, f"war_attack:{body.user_id}", {}, lambda: do_war_attack(db, user.id, body.user_id))


def finish_wars(db: Session) -> int:
    n = 0
    for w in db.scalars(select(GuildWar).where(GuildWar.status == "active", GuildWar.ends_at <= utcnow())
                        .with_for_update(skip_locked=True)).all():
        w.status = "finished"
        w.winner = w.guild_a if w.score_a > w.score_b else (w.guild_b if w.score_b > w.score_a else None)
        for gid in (w.guild_a, w.guild_b):
            g = db.get(Guild, gid)
            if g is None:
                continue
            won = w.winner == gid
            attackers = set(db.scalars(select(GuildWarAttack.user_id).where(GuildWarAttack.war_id == w.id,
                                                                            GuildWarAttack.guild_id == gid)))
            for x in members(db, gid):
                rw = dict(G()["war"]["win_reward" if won else "loss_reward"])
                if x.user_id not in attackers:  # base share for everyone active in the guild, full share for attackers
                    rw = {k: v // 2 for k, v in rw.items()}
                notify(db, x.user_id, "Война гильдий завершена",
                       ("Победа" if won else ("Ничья" if w.winner is None else "Поражение")) + f" ({w.score_a}:{w.score_b}).", rw)
            log(db, gid, None, "war_end", None, won=won)
        n += 1
    db.flush()
    return n


# ------------------------------------------------------------------ weekly rewards & inactivity (scheduler)
def weekly_rewards(db: Session) -> int:
    """Base reward for every active member + capped personal bonus: the strongest few never take everything."""
    wr = G()["week_rewards"]
    n = 0
    for g in db.scalars(select(Guild)).all():
        for x in members(db, g.id):
            pts = x.contribution_week or 0
            if pts >= wr["min_points_active"]:
                rw = dict(wr["base"])
                bonus = min(wr["max_bonus_marks"], pts * wr["per_point"]["guild_marks"])
                rw["guild_marks"] = rw.get("guild_marks", 0) + bonus
                notify(db, x.user_id, f"Недельная награда гильдии «{g.name}»",
                       f"Ваш вклад за неделю: {pts} очков. Базовая награда + личный бонус.", rw)
                n += 1
            x.contribution_week = 0
        g.week_points = 0
    db.flush()
    return n


def inactivity_scan(db: Session) -> int:
    now = utcnow()
    n = 0
    for x in db.scalars(select(GuildMember)).all():
        if x.last_active_at is None:
            x.last_active_at = now
            continue
        days = (now - as_utc(x.last_active_at)).days
        if days >= G()["inactive_warn_days"] and x.warned_at is None:
            x.warned_at = now
            g = db.get(Guild, x.guild_id)
            log(db, x.guild_id, None, "auto_warn", x.user_id, days=days)
            notify(db, x.user_id, "Гильдия ждёт вас", f"Вас не было {days} дн. Руководство гильдии «{g.name}» может исключить неактивных участников.")
            n += 1
        elif days < G()["inactive_warn_days"] and x.warned_at is not None:
            x.warned_at = None
        if x.role == "novice" and (now - as_utc(x.joined_at)).days >= G()["novice_promote_days"]:
            x.role = "member"
            log(db, x.guild_id, None, "role", x.user_id, old="novice", new="member", auto=True)
    db.flush()
    return n
