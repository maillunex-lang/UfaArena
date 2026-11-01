"""AI Director — the central coordinator of URALIA Living World AI (spec §5, stages 1, 3, 15, 17).

It does not contain game logic. Each tick it:
 1) receives game events (ai_events) and turns them into tasks;
 2) analyses the population (registered vs active, real online, load);
 3) starts play sessions by schedule and plans behaviour tasks for personas in session;
 4) assigns priorities and hands tasks to handlers (which call the same game code as the players' API);
 5) controls execution: leases, retries with backoff, recovery after a crash;
 6) watches the load: an adaptive budget shrinks when ticks get slow or the database is slow;
 7) writes results, metrics and a heartbeat (server_settings) for the admin panel.

Runs as a separate process (`python -m app.ai.director`, docker service `ai-director`) — one process for the
whole population, never one per persona. Modes: off / test (plan and log only) / normal / high / low.
"""
from __future__ import annotations

import logging
import random
import signal
import time
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_engine, init_engine, utcnow
from ..models import AiPersona, AiScheduleProfile, AiTask
from . import events as EV
from . import handlers as H
from . import hostload as HL
from . import memory as MEM
from . import personality as PERS
from . import population as POP
from . import schedules as SCH
from . import settings as ST
from . import tasks as TQ

log = logging.getLogger("uralia.ai.director")
_rng = random.Random()
PRIORITY = {"dm": 90, "mention": 70, "act": 50, "chat_keepalive": 30}


class Director:
    def __init__(self) -> None:
        self.budget: int | None = None
        self.last_population = -1e9  # monotonic clock may be small on a freshly booted machine: run first steps now
        self.last_compact = -1e9
        self.last_archive = -1e9
        self.sleeping = False
        self.last_social = {"outreach": -1e9, "guilds": -1e9, "groups": -1e9}
        self.slow_ticks = 0

    # ------------------------------------------------------------------ one tick
    def tick(self, db: Session) -> dict:
        t0 = time.perf_counter()
        s = ST.get(db)
        mode = s["mode"]
        if mode == "off":
            ST.write_status(db, {**ST.status(db), "mode": "off", "heartbeat": utcnow().isoformat(), "note": "Director выключен"})
            db.commit()
            return {"mode": "off"}
        acting = mode in ("normal", "high", "low")
        awake = ST.world_awake(db, s)
        if acting and awake and self.sleeping:
            self._wake_up(db)
        self.sleeping = not awake
        cap = max(1, int(s["max_tasks_per_tick"] * ST.MODE_FACTOR.get(mode, 1.0)))
        if self.budget is None:
            self.budget = max(2, cap // 2)
        self.budget = min(self.budget, cap)
        db_ms = self._db_latency(db)
        host = HL.snapshot()
        host_f = HL.factor(host, s)
        if host_f < 1.0:            # busy host: act less this tick, the adaptive budget recovers later
            self.budget = max(1, int(self.budget * host_f) or 1)
        load_factor = max(0.1, min(1.0, self.budget / cap)) * (0.5 if db_ms > 200 else 1.0) * host_f
        out = {"mode": mode, "budget": self.budget, "db_ms": round(db_ms, 1), "host": {**host, "factor": host_f}}

        out["recovered"] = TQ.recover_stale(db)
        now_mono = time.monotonic()
        if now_mono - self.last_population >= s["population_every_s"]:
            self.last_population = now_mono
            out["population"] = POP.grow(db, s, _rng, apply=acting)
            if acting:
                out["personalities"] = PERS.ensure(db, 50)
        target = POP.active_target(db, s, load_factor)
        out["active_target"] = target
        live = acting and awake  # nobody real online -> the AI residents sleep and cost nothing
        out["sleeping"] = not awake
        out["sessions_started"] = SCH.start_sessions(db, target, _rng) if live else 0
        out["events"] = self._events_to_tasks(db, s) if acting else 0
        out["planned"] = self._plan(db, acting) if (live or not acting) else 0
        db.commit()
        out["executed"], out["failed"] = self._execute(db, self.budget) if acting else (0, 0)
        if live:  # queued chat lines are posted on time (pacing: minimum gap, quiet after a discussion)
            from ..social.ai import banter
            from ..social.ai.control import global_switches
            if global_switches(db).get("chat", True):
                out["chat_posted"] = banter.flush(db)
                db.commit()

        if live and int(s.get("social_life", 0)):
            out.update(self._social(db, s, now_mono))
        ms_set = MEM.SECTION.get(db)
        if acting and now_mono - self.last_archive >= ms_set["archive_every_min"] * 60:
            self.last_archive = now_mono
            out["archived"] = MEM.archive(db, ms_set)
            db.commit()
        if now_mono - self.last_compact >= 600:
            self.last_compact = now_mono
            out["compacted"] = TQ.compact(db, s["compact_after_hours"])
            out["events_pruned"] = EV.prune(db)
        ms = (time.perf_counter() - t0) * 1000
        self._adapt(ms, s, cap)
        out["tick_ms"] = round(ms, 1)
        ST.write_status(db, {
            "mode": mode, "heartbeat": utcnow().isoformat(), "tick_ms": out["tick_ms"], "db_ms": out["db_ms"],
            "budget": self.budget, "budget_cap": cap, "host": out["host"], "active_target": target, "active_now": SCH.active_count(db),
            "registered": POP.registered(db), "real_online": POP.real_online(db), "queue": TQ.counts(db),
            "sleeping": out.get("sleeping", False),
            "events_pending": EV.pending(db), "last": {k: v for k, v in out.items() if k not in ("mode",)},
        })
        db.commit()
        return out

    # ------------------------------------------------------------------ steps
    def _social(self, db: Session, s: dict, now_mono: float) -> dict:
        """Phase 4: reaching out to real players, guild life, informal groups — each on its own cadence, isolated so a
        failure in one never breaks the tick."""
        from . import guild_ai as GAI
        from . import outreach as OUT
        out = {}
        for key, every, fn in (("outreach", s["outreach_every_s"], lambda: OUT.run(db, _rng)),
                               ("guilds", s["guilds_every_s"], lambda: GAI.run(db, _rng)),
                               ("groups", s["groups_every_s"], lambda: self._groups(db))):
            if now_mono - self.last_social[key] < every:
                continue
            self.last_social[key] = now_mono
            try:
                with db.begin_nested():
                    out[key] = fn()
                db.commit()
            except Exception as e:  # noqa: BLE001
                db.rollback()
                log.warning("social step %s failed: %s", key, e)
                out[key] = {"error": str(e)[:120]}
        return out

    def _groups(self, db: Session) -> dict:
        from datetime import timedelta as _td
        from ..models import PlayerProfile
        from . import social as SOC
        made = SOC.form_groups(db, _rng)
        joined = 0
        since = utcnow() - _td(minutes=15)
        for p in db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since).limit(30)):
            for r in SOC.who_likes(db, p.user_id, 0.3, 3):
                g = SOC.group_of(db, r.subject_id)
                if g is not None and SOC.maybe_add_real_player(db, g, p.user_id):
                    joined += 1
                    break
        return {"formed": made, "players_joined": joined}

    def _wake_up(self, db: Session) -> None:
        """The first real player came online: the chat may talk again right away and a few residents act soon."""
        from ..models import ServerSetting
        from ..social.ai import banter
        row = db.get(ServerSetting, banter.PAUSE_KEY)
        if row is not None:
            row.value = {}
        banter._queue.clear()  # lines planned before the night are stale
        log.info("AI residents wake up: a real player is online")

    def _db_latency(self, db: Session) -> float:
        t = time.perf_counter()
        db.execute(text("SELECT 1"))
        return (time.perf_counter() - t) * 1000

    def _events_to_tasks(self, db: Session, s: dict) -> int:
        n = 0
        for ev in EV.due(db, s["events_per_tick"], ("dm", "mention")):
            TQ.enqueue(db, ev.kind, f"ev:{ev.id}", priority=PRIORITY[ev.kind],
                       payload={**(ev.payload or {}), "persona_user_id": ev.persona_user_id}, max_attempts=2)
            EV.mark(ev)  # handed over in the same transaction as the task: no event is lost or doubled
            n += 1
        return n

    def _plan(self, db: Session, acting: bool) -> int:
        """Behaviour tasks for personas whose next action is due. Test mode records the decision as `simulated`
        and changes nothing in the world (the v1 engine keeps running)."""
        from ..social.ai import population as V1
        now = utcnow()
        q = select(AiPersona).where(AiPersona.active.is_(True), AiPersona.next_action_at <= now)
        if acting:
            q = q.where(AiPersona.session_until > now)
        profs = SCH.profiles(db)
        n = 0
        for persona in db.scalars(q.order_by(AiPersona.next_action_at).limit(max(4, (self.budget or 4) * 2))):
            prof: AiScheduleProfile | None = profs.get(persona.schedule_profile or "")
            action = V1._choose(persona)
            slot = as_utc(persona.next_action_at).strftime("%Y%m%d%H%M%S")
            pk = SCH.peak(persona, prof, now)
            t = TQ.enqueue(db, f"act:{action}", f"act:{persona.id}:{slot}", persona_id=persona.id,
                           priority=PRIORITY["act"] + (10 if pk else 0), payload={"peak": pk},
                           status="pending" if acting else "simulated")
            if t is not None:
                n += 1
                if not acting:
                    t.finished_at = now
            if acting:
                persona.next_action_at = now + H.next_action_delay(persona, pk)
        if acting and _rng.random() < 0.25:  # ambient AI-to-AI conversations, once per window
            TQ.enqueue(db, "chat_keepalive", f"chat:{now.strftime('%Y%m%d%H%M')}", priority=PRIORITY["chat_keepalive"])
        return n

    def _execute(self, db: Session, budget: int) -> tuple[int, int]:
        tasks = TQ.claim(db, budget)
        db.commit()  # leases are visible before work starts (crash -> recover_stale)
        done = failed = 0
        for t in tasks:
            tid = t.id
            try:
                with db.begin_nested():
                    res = H.run(db, t)
                    TQ.complete(t, res)  # action + completion in one transaction: idempotent
                db.commit()
                done += 1
            except Exception as e:  # one failing task never stops the tick
                db.rollback()
                row = db.get(AiTask, tid)
                if row is not None:
                    TQ.fail(row, f"{type(e).__name__}: {e}")
                db.commit()
                failed += 1
        return done, failed

    def _adapt(self, ms: float, s: dict, cap: int) -> None:
        """Graceful degradation (spec §8): shrink the budget when ticks are slow, grow it back slowly."""
        if ms > s["tick_budget_ms"]:
            self.slow_ticks += 1
            self.budget = max(2, int((self.budget or 2) * 0.7))
        else:
            self.slow_ticks = 0
            if ms < s["tick_budget_ms"] * 0.5:
                self.budget = min(cap, (self.budget or 2) + 1)


# ------------------------------------------------------------------ process entry point
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True


def main() -> None:
    from ..core.config import get_settings
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_engine(get_settings().database_url)
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    d = Director()
    log.info("AI Director started")
    while not _stop:
        tick_s = 5
        try:
            with Session(get_engine()) as db:
                tick_s = ST.get(db)["tick_seconds"]
                res = d.tick(db)
                if res.get("executed") or res.get("planned"):
                    log.info("tick %s", res)
        except Exception:
            log.exception("director tick failed")  # the next tick recovers (leases, idempotent tasks)
        for _ in range(int(tick_s * 10)):
            if _stop:
                break
            time.sleep(0.1)
    log.info("AI Director stopped")


if __name__ == "__main__":
    main()
