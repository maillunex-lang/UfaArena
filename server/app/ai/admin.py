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
from ..models import AdminAction, AiActivityLog, AiPersona, AiScheduleProfile, AiTask, PlayerProfile
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


@router.get("/characters")
def characters(query: str = Query("", max_length=32), only: str = Query("", max_length=16),
               limit: int = Query(50, ge=1, le=200), who: str = Depends(admin), db: Session = Depends(get_db)):
    """AI characters list for the admin panel: search by nickname / UR-id, filter "session" (playing now)."""
    from ..social.ai.personas import ARCHETYPES
    now = utcnow()
    q = select(AiPersona, PlayerProfile).join(PlayerProfile, PlayerProfile.user_id == AiPersona.user_id)
    if query:
        like = f"%{query.strip()}%"
        q = q.where(PlayerProfile.nickname.ilike(like) | PlayerProfile.uralia_id.ilike(like))
    if only == "session":
        q = q.where(AiPersona.session_until > now)
    elif only == "disabled":
        q = q.where(AiPersona.active.is_(False))
    rows = db.execute(q.order_by(PlayerProfile.power.desc()).limit(limit)).all()
    out = []
    for p, pr in rows:
        su = as_utc(p.session_until) if p.session_until else None
        out.append({"id": p.id, "nickname": pr.nickname, "uralia_id": pr.uralia_id, "level": pr.level, "power": pr.power,
                    "archetype": p.archetype, "archetype_desc": ARCHETYPES.get(p.archetype, {}).get("desc", ""),
                    "style": p.style, "schedule": p.schedule_profile, "active": p.active, "tier": p.tier,
                    "mood": p.mood, "version": p.personality_version,
                    "in_session": bool(su and su > now), "actions_today": p.actions_today if p.day == now.date().isoformat() else 0,
                    "last_action_at": as_utc(p.last_action_at).isoformat() if p.last_action_at else None})
    return {"items": out}


@router.post("/characters/{persona_id}/active")
def set_active(persona_id: str, body: dict, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Pause or resume one AI character (it is never deleted: progress and history stay)."""
    p = db.get(AiPersona, persona_id)
    if p is None:
        raise GameError("not_found", "ИИ-персонаж не найден", 404)
    p.active = bool(body.get("active"))
    if not p.active:
        p.session_until = None
    db.add(AdminAction(admin=who, action="ai_character_active", details={"persona": persona_id, "active": p.active}))
    db.commit()
    return {"ok": True, "active": p.active}


@router.get("/activity")
def activity(limit: int = Query(40, ge=1, le=200), who: str = Depends(admin), db: Session = Depends(get_db)):
    """Recent AI actions (what the living world did), newest first."""
    rows = db.execute(select(AiActivityLog, PlayerProfile.nickname)
                      .join(AiPersona, AiPersona.id == AiActivityLog.persona_id)
                      .join(PlayerProfile, PlayerProfile.user_id == AiPersona.user_id)
                      .order_by(AiActivityLog.id.desc()).limit(limit)).all()
    return {"items": [{"at": as_utc(a.created_at).isoformat(), "nickname": nick, "activity": a.activity,
                       "payload": a.payload} for a, nick in rows]}


# ------------------------------------------------------------------ phase 3: personalities, tiers, speech, memory
from ..models import AiArchetype, AiBiography, AiMemory, AiMemoryArchive, AiPersonaSnapshot  # noqa: E402
from . import llm as LLM  # noqa: E402
from . import memory as MEM  # noqa: E402
from . import personality as PERS  # noqa: E402
from . import speech as SP  # noqa: E402
from . import tiers as TR  # noqa: E402

SECTIONS = {"speech": SP.SECTION, "memory": MEM.SECTION, "tiers": TR.SECTION}


def _section(name: str):
    if name not in SECTIONS:
        raise GameError("not_found", "Нет такого раздела настроек", 404)
    return SECTIONS[name]


@router.get("/settings/{name}")
def get_section(name: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    out = _section(name).describe(db)
    if name == "speech":
        out["llm"] = LLM.status(out["settings"], db)
        out["providers"] = LLM.PROVIDERS
        out["keys"] = LLM.masked_keys(db)
    if name == "tiers":
        out["tiers"] = {k: {**{x: v[x] for x in ("name", "desc", "pace", "strategies")}, "levels": TR.tier_range(k),
                            "heroes": v["heroes"], "stars": v["stars"]} for k, v in TR.TIERS.items()}
        out["distribution"] = PERS.distribution(db)
        out["world_level"] = TR.world_level(db)
    return out


@router.post("/settings/{name}")
def set_section(name: str, body: dict, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        s = _section(name).update(db, body, who)
    except (ValueError, TypeError) as e:
        raise GameError("bad_settings", str(e), 400)
    db.commit()
    return {"settings": s}


@router.post("/settings/{name}/rollback")
def rollback_section(name: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        s = _section(name).rollback(db, who)
    except ValueError as e:
        raise GameError("no_history", str(e), 409)
    db.commit()
    return {"settings": s}


@router.get("/archetypes")
def get_archetypes(who: str = Depends(admin), db: Session = Depends(get_db)):
    rows = PERS.archetypes(db)
    counts = dict(db.execute(select(AiPersona.archetype, func.count()).group_by(AiPersona.archetype)).all())
    db.commit()
    return {"items": [{"code": a.code, "name": a.name, "description": a.description, "interests": a.interests,
                       "styles": a.styles, "trait_bias": a.trait_bias, "ambitions": a.ambitions, "weight": a.weight,
                       "enabled": a.enabled, "personas": counts.get(a.code, 0)} for a in rows.values()],
            "traits": PERS.TRAITS, "ambitions": PERS.AMBITIONS, "habits": PERS.HABITS,
            "interests": ["level", "chat", "arena", "guild", "friend", "raid", "event"],
            "styles": ["friendly", "joker", "grumpy", "flirty", "bro", "shy", "wise", "laconic", "competitive"]}


class ArchetypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field("", max_length=400)
    interests: list[str] = Field(default_factory=list, max_length=8)
    styles: list[str] = Field(default_factory=list, max_length=12)
    trait_bias: dict[str, float] = Field(default_factory=dict)
    ambitions: list[str] = Field(default_factory=list, max_length=8)
    weight: int = Field(1, ge=0, le=100)
    enabled: bool = True


@router.put("/archetypes/{code}")
def put_archetype(code: str, body: ArchetypeIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if not code.isidentifier() or len(code) > 32:
        raise GameError("bad_code", "Код архетипа: латиница, цифры, подчёркивание", 400)
    if any(t not in PERS.TRAITS or not -0.4 <= v <= 0.4 for t, v in body.trait_bias.items()):
        raise GameError("bad_bias", "Сдвиг черт: известные черты, от -0.4 до 0.4", 400)
    if any(a not in PERS.AMBITIONS for a in body.ambitions):
        raise GameError("bad_ambition", "Неизвестная амбиция", 400)
    if any(i not in ("level", "chat", "arena", "guild", "friend", "raid", "event") for i in body.interests):
        raise GameError("bad_interest", "Неизвестный интерес", 400)
    a = db.get(AiArchetype, code)
    if a is None:
        a = AiArchetype(code=code)
        db.add(a)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.add(AdminAction(admin=who, action="ai_archetype_put", details={"code": code, **body.model_dump()}))
    db.commit()
    return {"ok": True}


def _persona(db: Session, persona_id: str) -> AiPersona:
    p = db.get(AiPersona, persona_id)
    if p is None:
        raise GameError("not_found", "ИИ-персонаж не найден", 404)
    return p


def _mem(m: AiMemory, names: dict | None = None) -> dict:
    return {"id": m.id, "kind": m.kind, "kind_name": MEM.KINDS.get(m.kind, m.kind), "text": m.fact,
            "importance": m.importance, "subject": (names or {}).get(m.subject_user_id, m.subject_user_id),
            "persona_id": m.persona_id, "at": as_utc(m.created_at).isoformat() if m.created_at else None}


@router.get("/characters/{persona_id}")
def character(persona_id: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = _persona(db, persona_id)
    prof = db.get(PlayerProfile, p.user_id)
    mems = MEM.recall(db, p, limit=40)
    subj = {m.subject_user_id for m in mems if m.subject_user_id}
    names = {pp.user_id: pp.nickname for pp in db.scalars(select(PlayerProfile).where(PlayerProfile.user_id.in_(subj)))} if subj else {}
    b = db.get(AiBiography, p.id)
    snaps = db.scalars(select(AiPersonaSnapshot).where(AiPersonaSnapshot.persona_id == p.id).order_by(AiPersonaSnapshot.id.desc()))
    arch = db.scalars(select(AiMemoryArchive).where(AiMemoryArchive.persona_id == p.id).order_by(AiMemoryArchive.period.desc()))
    return {"id": p.id, "nickname": prof.nickname if prof else "", "uralia_id": prof.uralia_id if prof else "",
            "level": prof.level if prof else 0, "power": prof.power if prof else 0, "vip_level": prof.vip_level if prof else 0,
            "archetype": p.archetype, "style": p.style, "interests": p.interests, "backstory": p.backstory,
            "schedule": p.schedule_profile, "active": p.active, "strategy": (p.counters or {}).get("strategy"),
            "strategy_name": TR.STRATEGY_NAMES.get((p.counters or {}).get("strategy", ""), ""),
            "personality": PERS.describe(p), "memories": [_mem(m, names) for m in mems],
            "biography": list(b.entries or []) if b else [],
            "snapshots": [{"id": s.id, "version": s.version, "reason": s.reason, "by": s.created_by,
                           "at": as_utc(s.created_at).isoformat()} for s in snaps],
            "archive": [{"period": a.period, "stats": a.stats, "notes": a.notes[-10:]} for a in arch],
            "dict": {"traits": PERS.TRAITS, "ambitions": PERS.AMBITIONS, "habits": PERS.HABITS, "tiers":
                     {k: v["name"] for k, v in TR.TIERS.items()}, "kinds": MEM.KINDS, "bio": MEM.BIO_KINDS}}


class CharacterPatch(BaseModel):
    style: str | None = Field(None, max_length=24)
    backstory: str | None = Field(None, max_length=600)
    traits: dict[str, float] | None = None
    ambitions: list[str] | None = Field(None, max_length=6)
    habits: list[str] | None = Field(None, max_length=8)
    mood: float | None = Field(None, ge=-1, le=1)
    tier: str | None = Field(None, max_length=16)
    pace: float | None = Field(None, ge=0.1, le=5)


@router.patch("/characters/{persona_id}")
def patch_character(persona_id: str, body: CharacterPatch, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Administrative edit of a persona (stage 5/14): a checkpoint is taken first, so every edit can be undone."""
    p = _persona(db, persona_id)
    ch = body.model_dump(exclude_none=True)
    if not ch:
        raise GameError("no_changes", "Нет изменений", 400)
    if "traits" in ch and any(t not in PERS.TRAITS or not 0 <= v <= 1 for t, v in ch["traits"].items()):
        raise GameError("bad_traits", "Черты: известные, значения 0…1", 400)
    if "ambitions" in ch and any(a not in PERS.AMBITIONS for a in ch["ambitions"]):
        raise GameError("bad_ambition", "Неизвестная амбиция", 400)
    if "habits" in ch and any(h not in PERS.HABITS for h in ch["habits"]):
        raise GameError("bad_habit", "Неизвестная привычка", 400)
    if "tier" in ch and ch["tier"] not in TR.TIERS:
        raise GameError("bad_tier", "Неизвестный слой силы", 400)
    MEM.checkpoint(db, p, "Перед правкой администрации", who)
    if "traits" in ch:
        ch["traits"] = {**(p.traits or {}), **{k: round(v, 3) for k, v in ch["traits"].items()}}
    for k, v in ch.items():
        setattr(p, k, v)
    p.personality_version = (p.personality_version or 0) + 1
    MEM.bio_add(db, p, "admin", "Характер изменён администрацией: " + ", ".join(ch))
    db.add(AdminAction(admin=who, action="ai_character_edit", details={"persona": persona_id, **ch}))
    db.commit()
    return {"ok": True, "version": p.personality_version}


@router.post("/characters/{persona_id}/checkpoint")
def make_checkpoint(persona_id: str, body: dict | None = None, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = _persona(db, persona_id)
    reason = str((body or {}).get("reason") or "Ручная контрольная точка")[:160]
    s = MEM.checkpoint(db, p, reason, who, keep=MEM.SECTION.get(db)["snapshots_keep"])
    db.add(AdminAction(admin=who, action="ai_checkpoint", details={"persona": persona_id, "snapshot": s.id}))
    db.commit()
    return {"id": s.id}


@router.post("/characters/{persona_id}/restore/{snapshot_id}")
def restore_checkpoint(persona_id: str, snapshot_id: int, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = _persona(db, persona_id)
    snap = db.get(AiPersonaSnapshot, snapshot_id)
    if snap is None or snap.persona_id != p.id:
        raise GameError("not_found", "Контрольная точка не найдена", 404)
    MEM.restore(db, p, snap, who)
    db.commit()
    return {"ok": True, "version": p.personality_version}


@router.get("/characters/{persona_id}/export")
def export_character(persona_id: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = _persona(db, persona_id)
    out = MEM.export(db, p)
    db.add(AdminAction(admin=who, action="ai_persona_export", details={"persona": persona_id}))
    db.commit()
    return out


@router.post("/characters/{persona_id}/import")
def import_character(persona_id: str, body: dict, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = _persona(db, persona_id)
    try:
        MEM.import_into(db, p, body, who)
    except ValueError as e:
        raise GameError("bad_import", str(e), 400)
    db.commit()
    return {"ok": True, "version": p.personality_version}


@router.get("/memory/search")
def memory_search(q: str = Query("", max_length=80), kind: str = Query("", max_length=24),
                  persona_id: str = Query("", max_length=36), limit: int = Query(100, ge=1, le=500),
                  who: str = Depends(admin), db: Session = Depends(get_db)):
    rows = MEM.search(db, q, kind, persona_id, limit)
    pids = {m.persona_id for m in rows}
    nick = dict(db.execute(select(AiPersona.id, PlayerProfile.nickname).join(PlayerProfile, PlayerProfile.user_id == AiPersona.user_id)
                           .where(AiPersona.id.in_(pids))).all()) if pids else {}
    return {"items": [{**_mem(m), "persona": nick.get(m.persona_id, "")} for m in rows], "kinds": MEM.KINDS}


class MemoryPatch(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=200)
    kind: str | None = Field(None, max_length=24)
    importance: float | None = Field(None, ge=0, le=5)


@router.patch("/memory/{memory_id}")
def memory_edit(memory_id: int, body: MemoryPatch, who: str = Depends(admin), db: Session = Depends(get_db)):
    m = db.get(AiMemory, memory_id)
    if m is None:
        raise GameError("not_found", "Воспоминание не найдено", 404)
    if body.kind is not None and body.kind not in MEM.KINDS:
        raise GameError("bad_kind", "Неизвестный вид воспоминания", 400)
    old = {"text": m.fact, "kind": m.kind, "importance": m.importance}  # kept in the journal for restoring
    if body.text is not None:
        m.fact = body.text
    if body.kind is not None:
        m.kind = body.kind
    if body.importance is not None:
        m.importance = body.importance
    db.add(AdminAction(admin=who, action="ai_memory_edit", details={"memory": memory_id, "old": old,
                                                                    "new": body.model_dump(exclude_none=True)}))
    db.commit()
    return {"ok": True}


@router.post("/memory/archive-now")
def memory_archive_now(who: str = Depends(admin), db: Session = Depends(get_db)):
    r = MEM.archive(db)
    db.add(AdminAction(admin=who, action="ai_memory_archive", details=r))
    db.commit()
    return r


@router.get("/memory/stats")
def memory_stats(who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..models import AiActivityLog
    c = lambda m: db.scalar(select(func.count()).select_from(m)) or 0  # noqa: E731
    return {"memories": c(AiMemory), "activity_log": c(AiActivityLog), "archive_rows": c(AiMemoryArchive),
            "biographies": c(AiBiography), "snapshots": c(AiPersonaSnapshot),
            "by_kind": dict(db.execute(select(AiMemory.kind, func.count()).group_by(AiMemory.kind)).all())}


class LlmKeyIn(BaseModel):
    provider: str = Field(max_length=16)
    key: str = Field("", max_length=300)


@router.post("/llm/key")
def llm_key(body: LlmKeyIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Store (or clear with an empty key) a provider's API key on the server. Never returned in full or logged."""
    try:
        LLM.set_key(db, body.provider, body.key, who)
    except ValueError as e:
        raise GameError("bad_key", str(e), 400)
    db.commit()
    return {"keys": LLM.masked_keys(db)}


@router.post("/llm/test")
def llm_test(body: dict | None = None, who: str = Depends(admin), db: Session = Depends(get_db)):
    """One sample request to the selected (or given) provider: shows whether it works from this server."""
    provider = (body or {}).get("provider")
    if provider is not None and provider not in LLM.PROVIDERS:
        raise GameError("bad_provider", "Неизвестный поставщик", 400)
    r = LLM.test(db, SP.SECTION.get(db), provider)
    db.add(AdminAction(admin=who, action="ai_llm_test", details={"provider": provider or SP.SECTION.get(db)["llm_provider"],
                                                                 "ok": r.get("ok")}))
    db.commit()
    return r
