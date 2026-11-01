"""Living World AI phase 3: personalities (stage 2), power tiers (stage 4), speech + optional local model (stage 7),
long-term memory, archive, biography, checkpoints and transfer (stage 14) and their admin API."""
import random
from datetime import timedelta

import pytest

ADMIN = "phase3-admin-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def H():
    return {"X-Admin-Token": ADMIN, "X-Admin-Name": "tester"}


def _session():
    from app.core.db import get_db
    gen = get_db()
    return gen, next(gen)


def _new(db, n=1, seed=11):
    from app.social.ai.population import create_persona
    rng = random.Random(seed)
    out = [create_persona(db, rng) for _ in range(n)]
    db.commit()
    return out


def test_new_personas_have_individual_personality_tier_and_no_vip(client):
    from app.ai import tiers as TR
    from app.models import AiBiography, AiPersonaSnapshot, PlayerHero, PlayerProfile
    gen, db = _session()
    try:
        ps = _new(db, 40, seed=3)
        for p in ps:
            prof = db.get(PlayerProfile, p.user_id)
            assert p.tier in TR.TIERS and set(p.traits) >= {"bravery", "patience", "sociability", "ambition"}
            lo, hi = TR.tier_range(p.tier)
            assert lo <= prof.level <= hi
            assert prof.vip_level == 0  # §7: no fake evidence of payments
            heroes = db.query(PlayerHero).filter(PlayerHero.user_id == p.user_id).count()
            assert heroes >= 1
            assert p.ambitions and p.habits and p.voice
            assert db.get(AiBiography, p.id).entries[0]["kind"] == "created"
            assert db.query(AiPersonaSnapshot).filter(AiPersonaSnapshot.persona_id == p.id).count() == 1
        assert len({p.tier for p in ps}) >= 3
        # two personas of one archetype can be very different
        by_arch = {}
        for p in ps:
            by_arch.setdefault(p.archetype, []).append(p)
        pair = next(v for v in by_arch.values() if len(v) >= 2)
        diff = max(abs(pair[0].traits[t] - pair[1].traits[t]) for t in pair[0].traits)
        assert diff > 0.2
    finally:
        gen.close()


def test_existing_personas_get_personality_without_progress_change(client):
    from app.ai import personality as PERS
    from app.models import AiPersona, PlayerProfile
    gen, db = _session()
    try:
        p = _new(db, 1, seed=99)[0]
        prof = db.get(PlayerProfile, p.user_id)
        p.tier, p.traits, p.ambitions, p.habits, p.voice = None, {}, [], [], {}  # like a persona from phase 2
        db.commit()
        level, power = prof.level, prof.power
        assert PERS.ensure(db, 500) >= 1
        db.commit()
        db.refresh(p)
        assert p.tier and p.traits and db.get(PlayerProfile, p.user_id).level == level
        assert db.get(PlayerProfile, p.user_id).power == power
        # deterministic: the same persona gets the same character again
        t1 = dict(p.traits)
        p.tier, p.traits = None, {}
        db.commit()
        PERS.ensure(db, 500)
        db.commit()
        db.refresh(p)
        assert p.traits == t1
        assert db.query(AiPersona).filter(AiPersona.tier.is_(None)).count() == 0
    finally:
        gen.close()


def test_personality_evolves_versions_and_changes_behaviour(client):
    from app.ai import memory as MEM
    from app.ai import personality as PERS
    from app.models import AiPersonaSnapshot
    gen, db = _session()
    try:
        p = _new(db, 1, seed=5)[0]
        p.traits = {**p.traits, "ambition": 0.3, "bravery": 0.3}
        v0 = p.personality_version
        changed = False
        for _ in range(20):
            changed = PERS.evolve(db, p, "arena_win") or changed
        db.commit()
        assert changed and p.personality_version > v0
        assert p.traits["ambition"] > 0.4 and p.mood > 0.4
        assert any(m.kind == "personality" for m in MEM.recall(db, p, limit=10))
        assert db.query(AiPersonaSnapshot).filter(AiPersonaSnapshot.persona_id == p.id).count() >= 2
        # mood after defeats changes what the persona wants to do
        p.habits = ["breaks_after_loss"]
        p.mood = 0.0
        calm = PERS.action_weights(p, {"level": 3, "chat": 2, "arena": 3, "guild": 3, "friend": 1, "raid": 3, "event": 1, "war": 1})
        for _ in range(6):
            PERS.evolve(db, p, "arena_loss")
        upset = PERS.action_weights(p, {"level": 3, "chat": 2, "arena": 3, "guild": 3, "friend": 1, "raid": 3, "event": 1, "war": 1})
        assert p.mood < -0.4 and upset["arena"] < calm["arena"] and upset["level"] > calm["level"]
        p.counters = {**(p.counters or {}), "losses_row": 4}
        p.traits = {**p.traits, "patience": 0.2}
        assert PERS.wants_break(p, random.Random(1))
    finally:
        gen.close()


def test_tier_growth_respects_world_level(client):
    from app.ai import tiers as TR
    from app.models import PlayerProfile
    gen, db = _session()
    try:
        TR._world_cache.update(at=0.0, value=None)
        for i in range(5):
            from app.models import User
            u = User(kind="player")
            db.add(u)
            db.flush()
            db.add(PlayerProfile(user_id=u.id, uralia_id=f"UR-T{i:07d}", nickname=f"real_t{i}", level=12, is_ai=False,
                                     last_seen_at=__import__("app.core.db", fromlist=["utcnow"]).utcnow()))
        db.commit()
        TR._world_cache.update(at=0.0, value=None)
        w = TR.world_level(db)
        assert w is not None
        assert TR.level_cap(db, "regular") <= max(TR.tier_range("regular")[0], w + 8)
        assert TR.level_cap(db, "elite") == TR.tier_range("elite")[1]  # the elite may lead the world, within its range
    finally:
        TR._world_cache.update(at=0.0, value=None)
        gen.close()


def test_speech_voice_length_and_llm_fallback(client):
    from app.ai import llm as LLM
    from app.ai import speech as SP
    gen, db = _session()
    try:
        p = _new(db, 1, seed=8)[0]
        p.voice = {"emoji": 1.0, "exclaim": 0.0, "lowercase": False, "catchphrase": None, "emoji_set": ["🔥"]}
        s = {**SP.SECTION.defaults, "length": "short", "emotions": False}
        out = SP.stylize(random.Random(1), p, "Первое предложение. Второе предложение.", s)
        assert out.startswith("Первое предложение.") and "Второе" not in out and "🔥" in out
        assert len(SP.stylize(random.Random(1), p, "x" * 600, s)) <= 300
        # local model: enabled but not running -> templates keep working, no exception
        SP.SECTION.update(db, {"intelligence": 5, "llm_enabled": True, "llm_url": "http://127.0.0.1:9", "llm_timeout_s": 1,
                               "llm_min_free_mb": 512}, "test")
        db.commit()
        text, source = SP.compose(db, random.Random(2), p, "Привет!", to_user=None, user_text="как дела?", kind="greet")
        assert source == "template" and text
        st = LLM.status(SP.SECTION.get(db))
        assert st["enabled"] is True
        # not enough free memory -> the model is never called
        ok, why = LLM.availability({**SP.SECTION.get(db), "llm_min_free_mb": 262144})
        assert ok is False and "памяти" in why
        SP.SECTION.update(db, {"intelligence": 3, "llm_enabled": False}, "test")
        db.commit()
    finally:
        gen.close()


def test_memory_archive_keeps_history_and_biography_compacts(client):
    from app.ai import memory as MEM
    from app.core.db import utcnow
    from app.models import AiActivityLog, AiMemory, AiMemoryArchive
    gen, db = _session()
    try:
        p = _new(db, 1, seed=21)[0]
        old = utcnow() - timedelta(days=200)
        for i in range(30):
            db.add(AiActivityLog(persona_id=p.id, activity="arena", payload={}, created_at=old))
        db.add(AiActivityLog(persona_id=p.id, activity="arena", payload={}, created_at=utcnow()))
        db.add(AiMemory(persona_id=p.id, fact="Победил дракона", kind="victory", importance=4, created_at=old))
        db.add(AiMemory(persona_id=p.id, fact="Мелочь", kind="fact", importance=1, created_at=old))
        db.commit()
        r = MEM.archive(db)
        db.commit()
        assert r["activity"] >= 30 and r["memories"] >= 2
        arch = db.query(AiMemoryArchive).filter(AiMemoryArchive.persona_id == p.id).all()
        total = sum(a.stats.get("act:arena", 0) for a in arch)
        assert total == 30
        assert any(n["text"] == "Победил дракона" for a in arch for n in a.notes)
        assert db.query(AiActivityLog).filter(AiActivityLog.persona_id == p.id, AiActivityLog.activity == "arena").count() == 1
        # second run: nothing double-counted
        MEM.archive(db)
        db.commit()
        arch = db.query(AiMemoryArchive).filter(AiMemoryArchive.persona_id == p.id).all()
        assert sum(a.stats.get("act:arena", 0) for a in arch) == 30
        for i in range(150):
            MEM.bio_add(db, p, "milestone", f"Событие {i}", limit=40)
        db.commit()
        b = MEM.bio(db, p).entries
        assert len(b) <= 40 and b[0]["kind"] == "summary" and b[-1]["text"] == "Событие 149"
    finally:
        gen.close()


def test_admin_phase3_endpoints(client):
    gen, db = _session()
    try:
        p = _new(db, 1, seed=31)[0]
        pid = p.id
    finally:
        gen.close()
    assert client.get(f"/admin/api/ai/characters/{pid}").status_code in (401, 403)
    d = client.get(f"/admin/api/ai/characters/{pid}", headers=H()).json()
    assert d["personality"]["tier"] and d["biography"] and d["snapshots"]
    # edit -> checkpoint -> restore
    r = client.patch(f"/admin/api/ai/characters/{pid}", json={"traits": {"bravery": 0.99}, "mood": 0.5}, headers=H())
    assert r.status_code == 200
    assert client.patch(f"/admin/api/ai/characters/{pid}", json={"traits": {"bogus": 0.5}}, headers=H()).status_code == 400
    d2 = client.get(f"/admin/api/ai/characters/{pid}", headers=H()).json()
    assert next(t for t in d2["personality"]["traits"] if t["code"] == "bravery")["value"] == 0.99
    snap = next(s for s in d2["snapshots"] if s["reason"] == "Перед правкой администрации")
    assert client.post(f"/admin/api/ai/characters/{pid}/restore/{snap['id']}", headers=H()).status_code == 200
    d3 = client.get(f"/admin/api/ai/characters/{pid}", headers=H()).json()
    assert next(t for t in d3["personality"]["traits"] if t["code"] == "bravery")["value"] != 0.99
    # export / import (profile transfer)
    exp = client.get(f"/admin/api/ai/characters/{pid}/export", headers=H()).json()
    assert exp["format"] == "uralia-ai-persona/1"
    gen, db = _session()
    try:
        other = _new(db, 1, seed=32)[0].id
    finally:
        gen.close()
    assert client.post(f"/admin/api/ai/characters/{other}/import", json=exp, headers=H()).status_code == 200
    assert client.post(f"/admin/api/ai/characters/{other}/import", json={"x": 1}, headers=H()).status_code == 400
    # settings sections with validation and rollback
    s = client.get("/admin/api/ai/settings/speech", headers=H()).json()
    assert s["settings"]["llm_enabled"] is False and s["llm"]["available"] is False
    assert client.post("/admin/api/ai/settings/speech", json={"length": "huge"}, headers=H()).status_code == 400
    assert client.post("/admin/api/ai/settings/speech", json={"length": "long"}, headers=H()).json()["settings"]["length"] == "long"
    assert client.post("/admin/api/ai/settings/speech/rollback", headers=H()).json()["settings"]["length"] != "long"
    t = client.get("/admin/api/ai/settings/tiers", headers=H()).json()
    assert set(t["tiers"]) == {"newbie", "regular", "experienced", "veteran", "elite"}
    assert client.get("/admin/api/ai/settings/nope", headers=H()).status_code == 404
    # archetypes as data
    a = client.get("/admin/api/ai/archetypes", headers=H()).json()
    code = a["items"][0]["code"]
    body = {k: a["items"][0][k] for k in ("name", "description", "interests", "styles", "trait_bias", "ambitions", "weight", "enabled")}
    body["trait_bias"] = {"bravery": 0.3}
    assert client.put(f"/admin/api/ai/archetypes/{code}", json=body, headers=H()).status_code == 200
    body["trait_bias"] = {"bravery": 0.9}
    assert client.put(f"/admin/api/ai/archetypes/{code}", json=body, headers=H()).status_code == 400
    # memory search / edit / stats / archive now
    m = client.get(f"/admin/api/ai/memory/search?persona_id={pid}", headers=H()).json()["items"]
    if m:
        assert client.patch(f"/admin/api/ai/memory/{m[0]['id']}", json={"importance": 4}, headers=H()).status_code == 200
    assert "memories" in client.get("/admin/api/ai/memory/stats", headers=H()).json()
    assert "activity" in client.post("/admin/api/ai/memory/archive-now", headers=H()).json()


def test_v1_tick_and_director_run_with_personalities(client):
    from app.ai.director import Director
    from app.ai import settings as ST
    from app.core.db import utcnow
    from app.models import AiPersona, AiTask
    from app.social.ai import population as V1
    gen, db = _session()
    try:
        _new(db, 12, seed=41)
        for p in db.query(AiPersona).all():
            p.next_action_at = utcnow() - timedelta(seconds=5)
            p.schedule = {"hours": list(range(24))}
        db.commit()
        V1.tick(db)
        db.commit()
        ST.update(db, {"mode": "normal"}, "test")
        db.commit()
        d = Director()
        for _ in range(4):
            for p in db.query(AiPersona).all():
                p.next_action_at = utcnow() - timedelta(seconds=5)
            db.commit()
            d.tick(db)
        assert db.query(AiTask).filter(AiTask.status == "failed").count() == 0
        ST.update(db, {"mode": "test"}, "test")
        db.commit()
    finally:
        gen.close()


def test_chat_pacing_gap_and_quiet_after_discussion(client):
    from app.core.db import utcnow
    from app.models import ChatMessage
    from app.social.ai import banter
    gen, db = _session()
    try:
        ps = _new(db, 3, seed=77)
        ch = "guild:pacing-test"
        banter._queue.clear()
        banter._speech_cache.update(at=0.0, value=None)
        t0 = __import__("time").monotonic() - 1
        for i, p in enumerate(ps):
            banter._queue.append((t0, p.user_id, ch, f"реплика {i}"))
        assert banter.flush(db) == 1          # three lines due at once -> only one is posted
        db.commit()
        assert banter.flush(db) == 0          # the next waits for the 10-second gap
        n = db.query(ChatMessage).filter(ChatMessage.channel == ch).count()
        assert n == 1
        for m in db.query(ChatMessage).filter(ChatMessage.channel == ch):  # pretend 11 s passed
            m.created_at = utcnow() - timedelta(seconds=11)
        db.commit()
        assert banter.flush(db) == 1
        db.commit()
        assert not banter.in_pause(db, ch)     # discussion still going (one line left)
        for m in db.query(ChatMessage).filter(ChatMessage.channel == ch):
            m.created_at = utcnow() - timedelta(seconds=11)
        db.commit()
        assert banter.flush(db) == 1
        db.commit()
        assert banter.in_pause(db, ch)         # discussion over -> quiet for 5..15 minutes
        assert 5 * 60 - 5 <= banter.pause_left_s(db, ch) <= 15 * 60
        assert banter.start_conversation(db, ch, ps) == 0
        assert banter.ambient(db, ps[0], ch) == ""
    finally:
        banter._queue.clear()
        gen.close()


def test_llm_providers_keys_privacy_and_fallback(client, monkeypatch):
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from app.ai import llm as LLM
    from app.ai import speech as SP
    from app.models import AdminAction, PlayerProfile, User

    seen = {}

    class Fake(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["auth"] = self.headers.get("Authorization")
            seen["body"] = body
            mode = seen.get("mode", "ok")
            if mode == "429":
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"error":"rate"}')
                return
            text = {"ok": "Ставь танка вперёд и лекаря назад!", "bad": "Я человек, купи кристаллы"}[mode]
            out = _json.dumps({"choices": [{"message": {"content": text}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setitem(LLM.PROVIDERS, "groq", {**LLM.PROVIDERS["groq"], "url": f"http://127.0.0.1:{srv.server_port}/v1"})
    monkeypatch.delenv("URALIA_LLM_GROQ_KEY", raising=False)
    try:
        # no key -> not available, templates
        assert client.post("/admin/api/ai/settings/speech", headers=H(), json={
            "llm_enabled": True, "llm_provider": "groq", "intelligence": 5, "llm_model": ""}).status_code == 200
        st = client.get("/admin/api/ai/settings/speech", headers=H()).json()
        assert st["llm"]["available"] is False and "ключ" in st["llm"]["reason"]
        assert set(st["providers"]) == {"local", "groq", "google", "openrouter", "cloudflare", "huggingface"}
        # key stored on the server, masked, never logged
        secret = "gsk_test_SECRET_1234567890"
        r = client.post("/admin/api/ai/llm/key", headers=H(), json={"provider": "groq", "key": secret})
        assert r.status_code == 200 and r.json()["keys"]["groq"]["mask"] == "••••7890"
        st = client.get("/admin/api/ai/settings/speech", headers=H()).json()
        assert secret not in _json.dumps(st) and st["llm"]["available"] is True
        assert client.post("/admin/api/ai/llm/key", headers=H(), json={"provider": "local", "key": "x"}).status_code == 400
        # connection test through the selected provider
        t = client.post("/admin/api/ai/llm/test", headers=H(), json={"provider": "groq"}).json()
        assert t["ok"] is True and "танка" in t["text"] and seen["auth"] == f"Bearer {secret}"
        assert seen["body"]["model"] == "llama-3.3-70b-versatile"
        gen, db = _session()
        try:
            assert not any(secret in _json.dumps(a.details) for a in db.query(AdminAction).all())
            p = _new(db, 1, seed=91)[0]
            u = User(kind="player")
            db.add(u)
            db.flush()
            db.add(PlayerProfile(user_id=u.id, uralia_id="UR-LLMTEST1", nickname="Зарема77", level=5, is_ai=False))
            db.commit()
            # reply to a real player: nickname never leaves the server
            text, src = SP.compose(db, random.Random(3), p, "Привет!", to_user=u.id, user_text="Зарема77 тут, подскажи по арене",
                                   kind="arena")
            assert src == "llm" and "танка" in text
            sent = _json.dumps(seen["body"], ensure_ascii=False)
            assert "Зарема77" not in sent and "собеседник" in sent and "не человек" in sent
            # mentions in the public chat use templates unless allowed
            _, src2 = SP.compose(db, random.Random(3), p, "Привет!", to_user=u.id, user_text="вопрос", kind="arena", public=True)
            assert src2 == "template"
            # filter and provider errors fall back to templates
            seen["mode"] = "bad"
            assert SP.compose(db, random.Random(4), p, "Шаблон.", to_user=u.id, user_text="кто ты", kind="arena")[1] == "template"
            seen["mode"] = "429"
            assert SP.compose(db, random.Random(5), p, "Шаблон.", to_user=u.id, user_text="арена?", kind="arena")[1] == "template"
            assert "429" in LLM._state["last_error"]
        finally:
            gen.close()
        t = client.post("/admin/api/ai/llm/test", headers=H(), json={"provider": "cloudflare"}).json()
        assert t["ok"] is False and ("ключ" in t["error"] or "аккаунт" in t["error"])
    finally:
        srv.shutdown()
        client.post("/admin/api/ai/llm/key", headers=H(), json={"provider": "groq", "key": ""})
        client.post("/admin/api/ai/settings/speech", headers=H(), json={"llm_enabled": False, "llm_provider": "local",
                                                                         "intelligence": 3})
