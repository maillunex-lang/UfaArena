"""Admin API of the AI Director (phase 2 part of the AI Control Center, spec stage 18 grows it further).
Same admin authentication as the rest of /admin/api; every change is validated and logged (admin_actions)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.errors import GameError
from ..models import AdminAction, AiPersona, AiScheduleProfile, AiTask, PlayerProfile
from ..modules.admin import admin
from . import population as POP
from . import schedules as SCH
from . import settings as ST
from . import tasks as TQ

router = APIRouter(prefix="/admin/api/ai", tags=["ai-admin"])


@router.get("/director")
def director(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"settings": ST.get(db), "defaults": ST.DEFAULTS, "limits": ST.LIMITS, "modes": ST.MODES,
            "status": ST.status(db), "owns_world": ST.director_owns_world(db),
            "registered": POP.registered(db), "active_now": SCH.active_count(db), "queue": TQ.counts(db)}


@router.post("/director")
def set_director(body: dict, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        s = ST.update(db, body, who)
    except (ValueError, TypeError) as e:
        raise GameError("bad_settings", str(e), 400)
    db.commit()
    return {"settings": s}


@router.post("/director/rollback")
def rollback(who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        s = ST.rollback(db, who)
    except ValueError as e:
        raise GameError("no_history", str(e), 409)
    db.commit()
    return {"settings": s}


@router.get("/tasks")
def tasks(status: str | None = Query(None, max_length=16), kind: str | None = Query(None, max_length=48),
          limit: int = Query(50, ge=1, le=500), who: str = Depends(admin), db: Session = Depends(get_db)):
    q = select(AiTask)
    if status:
        q = q.where(AiTask.status == status)
    if kind:
        q = q.where(AiTask.kind == kind)
    rows = db.scalars(q.order_by(AiTask.id.desc()).limit(limit)).all()
    return {"items": [{"id": t.id, "key": t.key, "kind": t.kind, "persona_id": t.persona_id, "priority": t.priority,
                       "status": t.status, "attempts": t.attempts, "max_attempts": t.max_attempts,
                       "run_after": as_utc(t.run_after).isoformat(), "created_at": as_utc(t.created_at).isoformat(),
                       "result": t.result, "error": t.error} for t in rows], "counts": TQ.counts(db)}


@router.post("/tasks/{task_id}/retry")
def retry(task_id: int, who: str = Depends(admin), db: Session = Depends(get_db)):
    t = db.get(AiTask, task_id)
    if t is None:
        raise GameError("not_found", "Задача не найдена", 404)
    if t.status not in ("failed", "cancelled"):
        raise GameError("bad_state", "Повторить можно только неудачную или отменённую задачу", 409)
    t.status, t.attempts, t.error, t.run_after = "pending", 0, None, utcnow()
    db.add(AdminAction(admin=who, action="ai_task_retry", details={"task": task_id}))
    db.commit()
    return {"ok": True}


@router.get("/schedules")
def schedules(who: str = Depends(admin), db: Session = Depends(get_db)):
    SCH.ensure_profiles(db)
    counts = dict(db.execute(select(AiPersona.schedule_profile, func.count()).group_by(AiPersona.schedule_profile)).all())
    db.commit()
    return {"items": [{"code": p.code, "name": p.name, "hours": p.hours, "peak_hours": p.peak_hours, "tz_shift": p.tz_shift,
                       "session_minutes": p.session_minutes, "rest_weekdays": p.rest_weekdays, "weight": p.weight,
                       "personas": counts.get(p.code, 0)} for p in db.scalars(select(AiScheduleProfile))]}


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    hours: list[int] = Field(max_length=24)
    peak_hours: list[int] = Field(default_factory=list, max_length=24)
    tz_shift: int = Field(0, ge=-12, le=12)
    session_minutes: int = Field(40, ge=5, le=600)
    rest_weekdays: list[int] = Field(default_factory=list, max_length=7)
    weight: int = Field(1, ge=0, le=100)


@router.put("/schedules/{code}")
def put_schedule(code: str, body: ScheduleIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if not code.isidentifier() or len(code) > 32:
        raise GameError("bad_code", "Код профиля: латиница, цифры, подчёркивание", 400)
    if any(h < 0 or h > 23 for h in body.hours + body.peak_hours) or any(d < 0 or d > 6 for d in body.rest_weekdays):
        raise GameError("bad_schedule", "Часы 0–23, дни недели 0–6", 400)
    p = db.get(AiScheduleProfile, code)
    if p is None:
        p = AiScheduleProfile(code=code)
        db.add(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.add(AdminAction(admin=who, action="ai_schedule_put", details={"code": code, **body.model_dump()}))
    db.commit()
    return {"ok": True}


@router.post("/characters/{persona_id}/run")
def run_now(persona_id: str, action: str = Query("level", max_length=16), who: str = Depends(admin),
            db: Session = Depends(get_db)):
    """Manual launch of one persona (stage 15): starts a short session and queues the action with top priority."""
    from ..social.ai.population import ACTIONS
    p = db.get(AiPersona, persona_id)
    if p is None:
        raise GameError("not_found", "ИИ-персонаж не найден", 404)
    if action not in ACTIONS:
        raise GameError("bad_action", "Действия: " + ", ".join(ACTIONS), 400)
    now = utcnow()
    p.session_until = max(as_utc(p.session_until) if p.session_until else now, now + timedelta(minutes=15))
    t = TQ.enqueue(db, f"act:{action}", f"manual:{persona_id}:{now.isoformat()}", persona_id=persona_id, priority=95)
    db.add(AdminAction(admin=who, action="ai_run_now", details={"persona": persona_id, "action": action}))
    db.commit()
    return {"task_id": t.id if t else None, "note": "Выполнится, когда Director в рабочем режиме (обычный / повышенный / низкий)"}


@router.get("/population")
def population(who: str = Depends(admin), db: Session = Depends(get_db)):
    by_profile = dict(db.execute(select(AiPersona.schedule_profile, func.count()).group_by(AiPersona.schedule_profile)).all())
    by_arch = dict(db.execute(select(AiPersona.archetype, func.count()).group_by(AiPersona.archetype)).all())
    disabled = db.scalar(select(func.count()).select_from(AiPersona).where(AiPersona.active.is_(False))) or 0
    real = db.scalar(select(func.count()).select_from(PlayerProfile).where(PlayerProfile.is_ai.is_(False))) or 0
    return {"registered": POP.registered(db), "disabled": disabled, "active_now": SCH.active_count(db),
            "real_players": real, "real_online": POP.real_online(db), "by_schedule": by_profile, "by_archetype": by_arch}
