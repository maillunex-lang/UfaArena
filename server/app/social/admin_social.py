"""Owner/moderator tools for the online systems (same X-Admin-Token as the monetization admin).
Every write is logged in admin_actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db
from ..core.errors import GameError
from ..models import (
    AdminAction, Appeal, ChatMessage, ChatReport, Guild, PlayerProfile, Sanction, SuspicionFlag, WorldEvent, WorldState,
)
from ..modules.admin import admin
from . import moderation as M
from . import scheduler
from .common import by_public_id, card

router = APIRouter(prefix="/admin/api/social", tags=["admin-social"])


def _log(db: Session, who: str, action: str, **details) -> None:
    db.add(AdminAction(admin=who, action=action, details=details))


@router.get("/overview")
def overview(who: str = Depends(admin), db: Session = Depends(get_db)):
    from .ai.population import overview as ai_overview
    cnt = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(*w)) or 0  # noqa: E731
    return {
        "players": cnt(PlayerProfile, PlayerProfile.is_ai.is_(False)), "ai": ai_overview(db),
        "guilds": cnt(Guild, Guild.is_ai.is_(False)), "ai_guilds": cnt(Guild, Guild.is_ai.is_(True)),
        "open_reports": cnt(ChatReport, ChatReport.status == "open"), "open_flags": cnt(SuspicionFlag, SuspicionFlag.status == "open"),
        "open_appeals": cnt(Appeal, Appeal.status == "open"),
        "active_sanctions": cnt(Sanction, Sanction.status == "active"), "jobs": scheduler.status(),
    }


@router.get("/reports")
def reports(status: str = Query("open"), who: str = Depends(admin), db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(ChatReport).where(ChatReport.status == status).order_by(ChatReport.id.desc()).limit(100)):
        msg = db.get(ChatMessage, r.message_id) if r.message_id else None
        out.append({"id": r.id, "reason": r.reason, "comment": r.comment, "at": as_utc(r.created_at).isoformat(),
                    "target": card(db, r.target_id), "reporter": card(db, r.reporter_id)["nickname"],
                    "message": {"id": msg.id, "text": msg.text, "channel": msg.channel} if msg else None})
    return {"items": out}


class ReportAction(BaseModel):
    status: str = Field(pattern="^(actioned|dismissed)$")


@router.post("/reports/{rid}")
def report_action(rid: int, body: ReportAction, who: str = Depends(admin), db: Session = Depends(get_db)):
    r = db.get(ChatReport, rid)
    if r is None:
        raise GameError("not_found", "Жалоба не найдена", 404)
    r.status = body.status
    _log(db, who, "report_" + body.status, report=rid)
    db.commit()
    return {"ok": True}


class SanctionIn(BaseModel):
    uralia_id: str = Field(max_length=16)
    kind: str = Field(pattern="^(warning|mute|temp_ban|perm_ban)$")
    reason: str = Field(min_length=3, max_length=300)
    minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 365)


@router.post("/sanctions")
def sanction(body: SanctionIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = by_public_id(db, body.uralia_id)
    if p.is_ai:
        raise GameError("ai", "ИИ-персонажами управляет движок ИИ, санкции к ним не применяются")
    if body.kind in ("mute", "temp_ban") and not body.minutes:
        raise GameError("minutes", "Для мута и временной блокировки укажите срок")
    s = M.issue(db, p.user_id, body.kind, body.reason, body.minutes if body.kind != "perm_ban" else None, who)
    _log(db, who, "sanction", user=p.uralia_id, kind=body.kind, minutes=body.minutes, reason=body.reason)
    db.commit()
    return M.sanction_view(s)


@router.post("/sanctions/{sid}/revoke")
def sanction_revoke(sid: int, who: str = Depends(admin), db: Session = Depends(get_db)):
    s = db.get(Sanction, sid)
    if s is None:
        raise GameError("not_found", "Санкция не найдена", 404)
    M.revoke(db, s, who)
    _log(db, who, "sanction_revoke", sanction=sid)
    db.commit()
    return M.sanction_view(s)


@router.get("/appeals")
def appeals(who: str = Depends(admin), db: Session = Depends(get_db)):
    out = []
    for a in db.scalars(select(Appeal).order_by(Appeal.id.desc()).limit(100)):
        s = db.get(Sanction, a.sanction_id)
        out.append({"id": a.id, "status": a.status, "text": a.text, "resolution": a.resolution,
                    "player": card(db, a.user_id), "sanction": M.sanction_view(s) if s else None})
    return {"items": out}


class AppealDecision(BaseModel):
    accept: bool
    resolution: str = Field(default="", max_length=300)


@router.post("/appeals/{aid}")
def appeal_decide(aid: int, body: AppealDecision, who: str = Depends(admin), db: Session = Depends(get_db)):
    a = db.get(Appeal, aid)
    if a is None or a.status != "open":
        raise GameError("not_found", "Апелляция не найдена", 404)
    a.status = "accepted" if body.accept else "rejected"
    a.resolution = body.resolution
    if body.accept:
        s = db.get(Sanction, a.sanction_id)
        if s:
            M.revoke(db, s, who)
    _log(db, who, "appeal_" + a.status, appeal=aid)
    db.commit()
    return {"ok": True, "status": a.status}


@router.get("/flags")
def flags(status: str = Query("open"), who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"items": [{"id": f.id, "kind": f.kind, "score": f.score, "details": f.details, "status": f.status,
                       "at": as_utc(f.created_at).isoformat(), "player": card(db, f.user_id)}
                      for f in db.scalars(select(SuspicionFlag).where(SuspicionFlag.status == status)
                                          .order_by(SuspicionFlag.score.desc()).limit(100))]}


class FlagAction(BaseModel):
    status: str = Field(pattern="^(reviewed|dismissed)$")


@router.post("/flags/{fid}")
def flag_action(fid: int, body: FlagAction, who: str = Depends(admin), db: Session = Depends(get_db)):
    f = db.get(SuspicionFlag, fid)
    if f is None:
        raise GameError("not_found", "Флаг не найден", 404)
    f.status = body.status
    _log(db, who, "flag_" + body.status, flag=fid)
    db.commit()
    return {"ok": True}


@router.get("/players/{uralia_id}")
def player_lookup(uralia_id: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = by_public_id(db, uralia_id)
    return {"card": card(db, p.user_id),
            "sanctions": [M.sanction_view(s) for s in db.scalars(select(Sanction).where(Sanction.user_id == p.user_id).order_by(Sanction.id.desc()))],
            "reports_against": db.scalar(select(func.count()).select_from(ChatReport).where(ChatReport.target_id == p.user_id)) or 0,
            "flags": [{"kind": f.kind, "score": f.score, "status": f.status} for f in db.scalars(select(SuspicionFlag).where(SuspicionFlag.user_id == p.user_id))],
            "recent_messages": [{"id": m.id, "channel": m.channel, "text": m.text, "hidden": m.hidden}
                                for m in db.scalars(select(ChatMessage).where(ChatMessage.user_id == p.user_id).order_by(ChatMessage.id.desc()).limit(20))]}


@router.post("/messages/{mid}/hide")
def hide_message(mid: int, who: str = Depends(admin), db: Session = Depends(get_db)):
    m = db.get(ChatMessage, mid)
    if m is None:
        raise GameError("not_found", "Сообщение не найдено", 404)
    m.hidden = True
    _log(db, who, "message_hide", message=mid)
    db.commit()
    return {"ok": True}


@router.get("/jobs")
def jobs(who: str = Depends(admin)):
    return {"items": scheduler.status()}


@router.post("/jobs/{name}/run")
def job_run(name: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    if name not in scheduler.JOBS:
        raise GameError("not_found", "Нет такой задачи", 404)
    _log(db, who, "job_run", job=name)
    db.commit()
    return {"result": scheduler.run_job(name, force=True)}


@router.get("/world")
def world_versions(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"versions": [{"version": w.version, "reason": w.reason, "at": as_utc(w.created_at).isoformat(), "state": w.state}
                         for w in db.scalars(select(WorldState).order_by(WorldState.version.desc()).limit(20))],
            "events": [{"name": e.name, "status": e.status, "progress": e.progress, "goal": e.goal, "outcome": e.outcome}
                       for e in db.scalars(select(WorldEvent).order_by(WorldEvent.starts_at.desc()).limit(10))]}


class RestoreIn(BaseModel):
    version: int


@router.post("/world/restore")
def world_restore(body: RestoreIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    from .events import restore_world
    ws = restore_world(db, body.version, who)
    _log(db, who, "world_restore", version=body.version, new_version=ws.version)
    db.commit()
    return {"version": ws.version}


@router.get("/ai-switches")
def ai_switches(who: str = Depends(admin), db: Session = Depends(get_db)):
    from .ai.control import GLOBAL_NAMES, global_switches
    return {"switches": global_switches(db), "names": GLOBAL_NAMES}


@router.post("/ai-switches")
def ai_switches_set(body: dict, who: str = Depends(admin), db: Session = Depends(get_db)):
    from .ai.control import set_global
    out = set_global(db, body, who)
    db.commit()
    return {"switches": out}
