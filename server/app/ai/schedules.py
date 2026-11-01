"""Activity Scheduler data (stage 15): group schedule profiles, personal time-zone shifts, session length, rest days,
peak hours. A persona plays only inside a session; the Director starts sessions while the number of personas in
session is below the active target (registered ≠ active, stage 3)."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import AiPersona, AiScheduleProfile

MSK = 3  # server-side reference: Moscow time; personas get their own shift on top
DEFAULT_PROFILES = [
    dict(code="larks", name="Жаворонки", hours=list(range(6, 12)) + [19, 20, 21], peak_hours=[7, 8], session_minutes=30, weight=2),
    dict(code="daytime", name="Днём", hours=list(range(10, 19)), peak_hours=[13, 14], session_minutes=40, weight=2),
    dict(code="evening", name="Вечерние", hours=list(range(17, 24)), peak_hours=[20, 21, 22], session_minutes=60, weight=5),
    dict(code="owls", name="Совы", hours=[21, 22, 23, 0, 1, 2, 3], peak_hours=[23, 0], session_minutes=50, weight=2),
    dict(code="weekend", name="По выходным", hours=list(range(9, 24)), peak_hours=[12, 13, 14, 15, 16], session_minutes=90,
         rest_weekdays=[0, 1, 2, 3, 4], weight=1),
    dict(code="casual", name="Изредка", hours=[12, 19, 21], peak_hours=[], session_minutes=20, weight=2),
    dict(code="grinder", name="Усердные", hours=list(range(8, 24)), peak_hours=[18, 19, 20, 21, 22], session_minutes=90, weight=1),
]
TZ_SHIFTS = [-1, 0, 0, 0, 0, 1, 2, 2, 3, 4]  # Kaliningrad … Novosibirsk relative to Moscow


def ensure_profiles(db: Session) -> int:
    n = 0
    for p in DEFAULT_PROFILES:
        if db.get(AiScheduleProfile, p["code"]) is None:
            db.add(AiScheduleProfile(rest_weekdays=p.get("rest_weekdays", []), tz_shift=0, **{k: v for k, v in p.items() if k != "rest_weekdays"}))
            n += 1
    db.flush()
    return n


def profiles(db: Session) -> dict[str, AiScheduleProfile]:
    return {p.code: p for p in db.scalars(select(AiScheduleProfile))}


def assign(db: Session, rng: random.Random | None = None, limit: int = 500) -> int:
    """Gives personas without a group schedule a weighted profile and a personal time-zone shift."""
    rng = rng or random.Random()
    profs = list(profiles(db).values())
    if not profs:
        return 0
    n = 0
    for persona in db.scalars(select(AiPersona).where(AiPersona.schedule_profile.is_(None)).limit(limit)):
        p = rng.choices(profs, weights=[max(1, x.weight) for x in profs])[0]
        persona.schedule_profile = p.code
        sch = dict(persona.schedule or {})
        sch.setdefault("tz_shift", rng.choice(TZ_SHIFTS))
        persona.schedule = sch
        n += 1
    db.flush()
    return n


def local_now(persona: AiPersona, prof: AiScheduleProfile | None, now=None):
    now = now or utcnow()
    shift = MSK + (prof.tz_shift if prof else 0) + int((persona.schedule or {}).get("tz_shift", 0))
    return now + timedelta(hours=shift)


def awake(persona: AiPersona, prof: AiScheduleProfile | None, now=None) -> bool:
    if prof is None:  # legacy personal schedule (v1)
        sch = persona.schedule or {}
        hours = sch.get("hours") or list(range(24))
        return (now or utcnow()).hour in hours
    t = local_now(persona, prof, now)
    if t.weekday() in (prof.rest_weekdays or []):
        return False
    return t.hour in (prof.hours or [])


def peak(persona: AiPersona, prof: AiScheduleProfile | None, now=None) -> bool:
    return prof is not None and local_now(persona, prof, now).hour in (prof.peak_hours or [])


def in_session(persona: AiPersona, now=None) -> bool:
    now = now or utcnow()
    return persona.session_until is not None and as_utc(persona.session_until) > now


def active_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiPersona).where(
        AiPersona.active.is_(True), AiPersona.session_until > utcnow())) or 0


def start_sessions(db: Session, target: int, rng: random.Random, limit: int = 40) -> int:
    """Start play sessions for awake personas until `target` personas are in session (peak hours are favoured)."""
    now = utcnow()
    need = target - active_count(db)
    if need <= 0:
        return 0
    profs = profiles(db)
    started = 0
    cands = list(db.scalars(select(AiPersona).where(AiPersona.active.is_(True), (AiPersona.session_until.is_(None)) |
                                                    (AiPersona.session_until <= now)).limit(limit * 6)))
    rng.shuffle(cands)
    for persona in cands:
        if started >= min(need, limit):
            break
        prof = profs.get(persona.schedule_profile or "")
        if not awake(persona, prof, now):
            continue
        if not peak(persona, prof, now) and rng.random() < 0.5:
            continue  # off-peak: only every other awake persona logs in
        minutes = int((prof.session_minutes if prof else 40) * rng.uniform(0.6, 1.4))
        persona.session_until = now + timedelta(minutes=minutes)
        persona.next_action_at = now + timedelta(seconds=rng.randint(5, 90))
        started += 1
    db.flush()
    return started
