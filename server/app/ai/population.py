"""Population Manager (stages 1, 3): permanent registry of AI personas with dynamic activity.

- Registered personas grow gradually towards `registered_target` (500 by default) and are never deleted for
  inactivity; an admin may disable a persona (`active=false`), which also never deletes history.
- How many personas play right now (in a session) is a separate number — the active target, derived from real
  online, the mode and the measured load.
Persona creation reuses the v1 registry (`app.social.ai.population.create_persona`) — one registry, no duplicate."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AiPersona, PlayerProfile
from . import schedules as SCH
from . import settings as ST


def registered(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiPersona)) or 0


def real_online(db: Session, minutes: int = 10) -> int:
    since = utcnow() - timedelta(minutes=minutes)
    return db.scalar(select(func.count()).select_from(PlayerProfile).where(
        PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)) or 0


def active_target(db: Session, s: dict, load_factor: float) -> int:
    """More real players online -> a livelier world, within [active_min, active_max]; mode and load scale it."""
    base = s["active_min"] + 3 * real_online(db)
    t = int(base * ST.MODE_FACTOR.get(s["mode"], 1.0) * max(0.1, min(1.0, load_factor)))
    return max(min(s["active_min"], s["active_max"]), min(s["active_max"], t))


def grow(db: Session, s: dict, rng: random.Random, apply: bool) -> dict:
    """Create up to `spawn_per_run` personas towards the target. In test mode only reports what it would do."""
    have = registered(db)
    want = max(0, min(s["spawn_per_run"], s["registered_target"] - have))
    created = 0
    if apply and want:
        from ..social.ai.population import create_persona, ensure_ai_guilds
        for _ in range(want):
            create_persona(db, rng)
            created += 1
        ensure_ai_guilds(db)
    SCH.ensure_profiles(db)
    assigned = SCH.assign(db, rng) if apply else 0
    db.flush()
    return {"registered": have + created, "target": s["registered_target"], "created": created,
            "would_create": want if not apply else 0, "assigned_schedules": assigned}
