"""Living World AI phase 2 — AI Director core: task queue idempotency, retries and crash recovery, modes, sessions,
registry growth, v1 fallback, adaptive budget and the admin API."""
import random
from datetime import timedelta

import pytest

ADMIN = "director-admin-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def H():
    return {"X-Admin-Token": ADMIN, "X-Admin-Name": "tester"}


def _session():
    from app.core.db import get_db
    gen = get_db()
    return gen, next(gen)


def _set(db, **kw):
    from app.ai import settings as ST
    ST.update(db, kw, "test")
    db.commit()


def _personas(db, n):
    from sqlalchemy import func, select
    from app.models import AiPersona
    from app.social.ai.population import create_persona
    have = db.scalar(select(func.count()).select_from(AiPersona)) or 0
    rng = random.Random(7)
    for _ in range(max(0, n - have)):
        create_persona(db, rng)
    db.commit()


def test_task_queue_idempotent_retry_and_recovery(client):
    from app.ai import tasks as TQ
    from app.core.db import utcnow
    gen, db = _session()
    try:
        a = TQ.enqueue(db, "act:level", "unit:k1", priority=10)
        assert a is not None and TQ.enqueue(db, "act:level", "unit:k1") is None  # same key -> no duplicate
        db.commit()
        claimed = [t for t in TQ.claim(db, 50) if t.key == "unit:k1"]
        assert claimed and claimed[0].status == "running" and claimed[0].attempts == 1
        t = claimed[0]
        TQ.fail(t, "boom")
        assert t.status == "pending" and t.run_after > utcnow()  # backoff
        t.run_after = utcnow() - timedelta(seconds=1)
        t.max_attempts = 2
        db.commit()
        t = [x for x in TQ.claim(db, 50) if x.key == "unit:k1"][0]
        t.lease_until = utcnow() - timedelta(seconds=1)  # the process "crashed" holding the lease
        db.commit()
        assert TQ.recover_stale(db) >= 1
        assert t.status == "failed"  # second attempt exhausted max_attempts=2
        t.created_at = utcnow() - timedelta(days=3)
        db.commit()
        assert TQ.compact(db, 24) >= 1
        db.commit()
    finally:
        gen.close()


def test_test_mode_plans_without_changing_the_world(client):
    from sqlalchemy import select
    from app.ai.director import Director
    from app.core.db import utcnow
    from app.models import AiPersona, AiTask, PlayerProfile
    gen, db = _session()
    try:
        _personas(db, 12)
        _set(db, mode="test", population_every_s=60)
        for p in db.scalars(select(AiPersona)):
            p.next_action_at = utcnow() - timedelta(minutes=1)
        db.commit()
        before = {p.user_id: p.level for p in db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True)))}
        out = Director().tick(db)
        assert out["mode"] == "test" and out["planned"] >= 1 and out["executed"] == 0
        sims = db.scalars(select(AiTask).where(AiTask.status == "simulated")).all()
        assert sims and all(t.kind.startswith("act:") for t in sims)
        after = {p.user_id: p.level for p in db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True)))}
        assert before == after  # nothing changed
        # a second tick re-plans the same slots -> idempotent, no new simulated rows for them
        n = len(sims)
        Director().tick(db)
        assert len(db.scalars(select(AiTask).where(AiTask.status == "simulated")).all()) == n
        from app.ai.settings import director_owns_world
        assert director_owns_world(db) is False  # test mode never takes the world from v1
    finally:
        gen.close()


def test_normal_mode_sessions_tasks_and_v1_fallback(client):
    from sqlalchemy import select
    from app.ai import settings as ST
    from app.ai.director import Director
    from app.core.db import utcnow
    from app.models import AiPersona, AiTask, AiScheduleProfile
    from app.ai import schedules as SCH
    gen, db = _session()
    try:
        _personas(db, 12)
        _set(db, mode="normal", active_min=6, active_max=6, population_every_s=60, registered_target=0)
        SCH.ensure_profiles(db)
        allday = db.get(AiScheduleProfile, "allday_test") or AiScheduleProfile(
            code="allday_test", name="Тест", hours=list(range(24)), peak_hours=list(range(24)), tz_shift=0,
            session_minutes=30, rest_weekdays=[], weight=0)
        db.add(allday)
        for p in db.scalars(select(AiPersona)):
            p.schedule_profile, p.session_until, p.next_action_at = "allday_test", None, utcnow() - timedelta(minutes=1)
        db.commit()
        d = Director()
        out = d.tick(db)
        assert out["sessions_started"] >= 1 and SCH.active_count(db) <= 6
        for p in db.scalars(select(AiPersona).where(AiPersona.session_until > utcnow())):
            p.next_action_at = utcnow() - timedelta(seconds=1)  # a session starts with a short human-like pause
        db.commit()
        out2 = d.tick(db)
        done = db.scalars(select(AiTask).where(AiTask.status == "done")).all()
        assert out["executed"] + out2["executed"] >= 1 and done
        assert ST.director_owns_world(db) is True
        # the API scheduler skips the v1 engine while the Director is alive …
        from app.social.scheduler import _ai_tick
        assert _ai_tick(db) == {"skipped": "AI Director"}
        # … and takes over again when the heartbeat is stale (Director crashed)
        st = ST.status(db)
        st["heartbeat"] = (utcnow() - timedelta(minutes=10)).isoformat()
        ST.write_status(db, st)
        db.commit()
        assert ST.director_owns_world(db) is False
        assert "skipped" not in _ai_tick(db)
        _set(db, mode="test")
    finally:
        gen.close()


def test_registry_grows_gradually_and_adaptive_budget(client):
    from app.ai import population as POP
    from app.ai import settings as ST
    from app.ai.director import Director
    gen, db = _session()
    try:
        have = POP.registered(db)
        s = {**ST.get(db), "registered_target": have + 3, "spawn_per_run": 2}
        r = POP.grow(db, s, random.Random(1), apply=False)
        assert r["created"] == 0 and r["would_create"] == 2  # test mode: report only
        r = POP.grow(db, s, random.Random(1), apply=True)
        assert r["created"] == 2 and POP.registered(db) == have + 2
        r = POP.grow(db, s, random.Random(2), apply=True)
        assert r["created"] == 1  # stops at the target
        db.commit()
        d = Director()
        d.budget = 10
        d._adapt(5000, {"tick_budget_ms": 1500}, 12)
        assert d.budget == 7  # slow tick -> shrink
        d._adapt(100, {"tick_budget_ms": 1500}, 12)
        assert d.budget == 8  # fast tick -> grow slowly
    finally:
        gen.close()


def test_director_admin_api_validation_rollback_and_manual_run(client):
    r = client.get("/admin/api/ai/director", headers=H())
    assert r.status_code == 200 and set(r.json()["modes"]) == {"off", "test", "normal", "high", "low"}
    assert client.get("/admin/api/ai/director").status_code in (401, 403)  # admin only
    assert client.post("/admin/api/ai/director", json={"mode": "chaos"}, headers=H()).status_code == 400
    assert client.post("/admin/api/ai/director", json={"max_tasks_per_tick": 100000}, headers=H()).status_code == 400
    assert client.post("/admin/api/ai/director", json={"mode": "low", "max_tasks_per_tick": 8}, headers=H()).json()["settings"]["mode"] == "low"
    back = client.post("/admin/api/ai/director/rollback", headers=H()).json()["settings"]
    assert back["mode"] != "low" or back["max_tasks_per_tick"] != 8
    sch = client.get("/admin/api/ai/schedules", headers=H()).json()["items"]
    assert {"evening", "owls", "weekend"} <= {x["code"] for x in sch}
    assert client.put("/admin/api/ai/schedules/bad-code!", json={"name": "x", "hours": [1]}, headers=H()).status_code == 400
    assert client.put("/admin/api/ai/schedules/lunch", json={"name": "Обеденные", "hours": [12, 13], "session_minutes": 25},
                      headers=H()).status_code == 200
    pop = client.get("/admin/api/ai/population", headers=H()).json()
    assert pop["registered"] >= 1
    from sqlalchemy import select
    from app.models import AiPersona
    gen, db = _session()
    try:
        pid = db.scalars(select(AiPersona.id).limit(1)).first()
    finally:
        gen.close()
    r = client.post(f"/admin/api/ai/characters/{pid}/run?action=chat", headers=H())
    assert r.status_code == 200 and r.json()["task_id"]
    assert client.get("/admin/api/ai/tasks?status=pending", headers=H()).json()["items"]


def test_host_load_guard_scales_activity():
    from app.ai import hostload as HL
    from app.ai import settings as ST
    s = dict(ST.DEFAULTS)
    assert HL.factor({"cpus": 1, "load1": 0.2, "mem_avail_mb": 1000}, s) == 1.0
    assert HL.factor({"cpus": 1, "load1": 0.9, "mem_avail_mb": 1000}, s) == 0.5
    assert HL.factor({"cpus": 1, "load1": 2.0, "mem_avail_mb": 1000}, s) == 0.2
    assert HL.factor({"cpus": 1, "load1": 0.2, "mem_avail_mb": 150}, s) == 0.2
    assert HL.factor({"cpus": 1, "load1": None, "mem_avail_mb": None}, s) == 1.0
    snap = HL.snapshot()
    assert snap["cpus"] >= 1


def test_admin_panel_ai_tab_characters_pause_activity(client):
    gen, db = _session()
    try:
        _personas(db, 6)
    finally:
        gen.close()
    assert client.get("/admin/api/ai/characters").status_code in (401, 403)
    lst = client.get("/admin/api/ai/characters", headers=H()).json()["items"]
    assert len(lst) >= 6 and all("nickname" in c and "archetype" in c for c in lst)
    one = lst[0]
    found = client.get(f"/admin/api/ai/characters?query={one['uralia_id']}", headers=H()).json()["items"]
    assert [c["id"] for c in found] == [one["id"]]
    r = client.post(f"/admin/api/ai/characters/{one['id']}/active", json={"active": False}, headers=H())
    assert r.status_code == 200 and r.json()["active"] is False
    paused = client.get("/admin/api/ai/characters?only=disabled", headers=H()).json()["items"]
    assert one["id"] in [c["id"] for c in paused]
    assert client.post(f"/admin/api/ai/characters/{one['id']}/active", json={"active": True}, headers=H()).json()["active"]
    assert "items" in client.get("/admin/api/ai/activity", headers=H()).json()
    page = client.get("/admin").text
    assert "['ai','ИИ-жители']" in page and "async ai()" in page


def test_ai_sleep_when_no_real_players_and_wake_up(client):
    from datetime import timedelta as _td
    from app.ai import settings as ST
    from app.ai.director import Director
    from app.core.db import utcnow as _now
    from app.models import AiTask, PlayerProfile, ServerSetting
    gen, db = _session()
    try:
        _personas(db, 10)
        real = db.query(PlayerProfile).filter(PlayerProfile.is_ai.is_(False)).all()
        saved = {p.user_id: p.last_seen_at for p in real}
        for p in real:
            p.last_seen_at = _now() - _td(hours=5)  # everybody left long ago
        _set(db, mode="normal")
        assert ST.world_awake(db) is False
        d = Director()
        before = db.query(AiTask).count()
        out = d.tick(db)
        assert out["sleeping"] is True and out["sessions_started"] == 0 and out["planned"] == 0
        assert db.query(AiTask).count() == before
        assert ST.status(db)["sleeping"] is True
        # a real player comes online -> next tick wakes the residents, the chat pause is lifted
        db.add(ServerSetting(key="ai_chat_pause", value={"global": (_now() + _td(minutes=10)).isoformat()})) \
            if db.get(ServerSetting, "ai_chat_pause") is None else None
        db.commit()
        if real:
            real[0].last_seen_at = _now()
        else:
            from app.models import User
            u = User(kind="player")
            db.add(u)
            db.flush()
            db.add(PlayerProfile(user_id=u.id, uralia_id="UR-WAKE0001", nickname="waker", level=3, is_ai=False,
                                 last_seen_at=_now()))
        db.commit()
        out = d.tick(db)
        from app.ai import schedules as SCH
        assert out["sleeping"] is False
        assert out["sessions_started"] > 0 or SCH.active_count(db) >= out["active_target"]
        assert not (db.get(ServerSetting, "ai_chat_pause").value or {})
        # sleeping can be switched off in the settings
        for p in db.query(PlayerProfile).filter(PlayerProfile.is_ai.is_(False)):
            p.last_seen_at = _now() - _td(hours=5)
        _set(db, sleep_when_empty=0)
        assert ST.world_awake(db) is True
        _set(db, sleep_when_empty=1, mode="test")
        for uid, ls in saved.items():
            db.get(PlayerProfile, uid).last_seen_at = ls
        db.commit()
    finally:
        gen.close()
