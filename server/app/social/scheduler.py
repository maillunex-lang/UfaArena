"""Background job queue for the online systems. Runs inside the API process (modular monolith); a DB lease
per job (job_runs) makes it safe with several workers or containers — only one runs a job at a time.
Every job is idempotent, so a crash mid-run is recovered by the next run."""
from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_engine, utcnow
from ..models import JobRun, RaidInstance
from .common import cfg, week_key

log = logging.getLogger("uralia.jobs")


def _ai_tick(db):
    from .ai.population import tick
    return tick(db)


def _ai_population(db):
    from .ai.population import ensure_population
    return ensure_population(db)


def _tournaments(db):
    from .tournaments import advance
    return {"rounds": advance(db)}


def _events(db):
    from .events import ensure, finish_due
    ensure(db)
    return {"finished": finish_due(db)}


def _guild_expeditions(db):
    from .guilds import settle_expeditions
    return {"settled": settle_expeditions(db)}


def _guild_wars(db):
    from .guilds import finish_wars
    return {"finished": finish_wars(db)}


def _guild_weekly(db):
    jr = db.get(JobRun, "guild_weekly_marker")
    wk = week_key()
    if jr is None:
        db.add(JobRun(name="guild_weekly_marker", last_status=wk))
        return {"skipped": "first week marker"}
    if jr.last_status == wk:
        return {"skipped": "already paid"}
    from .guilds import weekly_rewards
    n = weekly_rewards(db)
    jr.last_status = wk
    return {"rewarded": n}


def _inactivity(db):
    from .guilds import inactivity_scan
    return {"warned": inactivity_scan(db)}


def _sanctions(db):
    from .moderation import expire
    return {"expired": expire(db)}


def _economy(db):
    from .anticheat import economy_scan
    return economy_scan(db)


def _arena_season(db):
    from .arena import current_season
    return {"season": current_season(db).id}


def _raids(db):
    from .raids import finish
    n = 0
    for inst in db.scalars(select(RaidInstance).where(RaidInstance.status == "active", RaidInstance.ends_at <= utcnow())).all():
        finish(db, inst, expired=True)
        n += 1
    return {"expired": n}


JOBS: dict[str, tuple[int, callable]] = {
    "ai_tick": (15, _ai_tick),
    "ai_population": (600, _ai_population),
    "tournaments": (300, _tournaments),
    "events": (300, _events),
    "guild_expeditions": (300, _guild_expeditions),
    "guild_wars": (600, _guild_wars),
    "guild_weekly": (1800, _guild_weekly),
    "inactivity": (21600, _inactivity),
    "sanctions": (300, _sanctions),
    "economy": (3600, _economy),
    "arena_season": (1800, _arena_season),
    "raids": (600, _raids),
}


def run_job(name: str, force: bool = False) -> dict:
    interval, fn = JOBS[name]
    now = utcnow()
    with Session(get_engine()) as db:
        jr = db.get(JobRun, name, with_for_update=True)
        if jr is None:
            jr = JobRun(name=name, runs=0)
            db.add(jr)
            db.flush()
        if not force:
            if jr.lease_until and as_utc(jr.lease_until) > now:
                return {"skipped": "leased"}
            if jr.last_run_at and (now - as_utc(jr.last_run_at)).total_seconds() < interval:
                return {"skipped": "not due"}
        jr.lease_until = now + timedelta(seconds=max(60, interval))
        db.commit()
    status: dict
    with Session(get_engine()) as db:
        try:
            status = fn(db) or {}
            db.commit()
        except Exception as e:
            db.rollback()
            log.error("job %s failed: %s", name, traceback.format_exc())
            status = {"error": str(e)[:180]}
    with Session(get_engine()) as db:
        jr = db.get(JobRun, name)
        jr.lease_until = None
        jr.last_run_at = utcnow()
        jr.runs = (jr.runs or 0) + 1
        jr.last_status = str(status)[:200]
        db.commit()
    return status


def run_due() -> dict:
    out = {}
    for name in JOBS:
        out[name] = run_job(name)
    return out


def status() -> list[dict]:
    with Session(get_engine()) as db:
        rows = {j.name: j for j in db.scalars(select(JobRun))}
    return [{"name": n, "interval_s": JOBS[n][0], "last_run_at": as_utc(rows[n].last_run_at).isoformat() if n in rows and rows[n].last_run_at else None,
             "runs": rows[n].runs if n in rows else 0, "last_status": rows[n].last_status if n in rows else ""} for n in JOBS]


async def loop() -> None:
    tick = cfg()["scheduler"]["tick_seconds"]
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(None, run_due)
        except Exception:
            log.error("scheduler loop: %s", traceback.format_exc())
        await asyncio.sleep(tick)


def enabled() -> bool:
    if os.environ.get("URALIA_SCHEDULER", "").lower() in ("0", "off", "false"):
        return False
    from ..core.config import get_settings
    return cfg()["scheduler"]["enabled"] and get_settings().env != "test"
