"""Living World AI phase 5: AI play by the game rules (stages 5, 12; D-02), PvP (stage 10; D-03), economy safety
(stage 11; D-04), events (stage 13; D-05), per-AI administration."""
import random
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from tests.test_social import AH, ADMIN, session  # noqa: F401

ALLOWED_INCOME = {"afk_claim", "campaign_reward", "quest_reward", "mail_claim", "admin_ai", "battlepass", "event_reward"}


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def _ai(db, n, seed):
    from app.social.ai.population import create_persona
    rng = random.Random(seed)
    out = [create_persona(db, rng) for _ in range(n)]
    db.flush()
    return out


def test_play_session_by_the_rules_no_free_currency_no_vip(client):
    from app.ai import play as PLAY
    from app.core.db import utcnow
    from app.models import AiPersona, PlayerProfile, WalletTransaction
    from app.services import ledger_consistent
    with session() as db:
        p = _ai(db, 1, 1001)[0]
        db.get(PlayerProfile, p.user_id).afk_last_claim_at = utcnow() - timedelta(hours=8)
        pid, uid = p.id, p.user_id
    with session() as db:
        p = db.get(AiPersona, pid)
        log = PLAY.session(db, p, "T1", random.Random(1))
        assert "afk" in log["steps"] and "battle" in log["steps"] and "complete" in log["steps"], log
        incomes = {t.reason for t in db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == uid,
                                                                                 WalletTransaction.delta > 0))}
        assert incomes and incomes <= ALLOWED_INCOME, incomes  # resources only from the players' sources
        assert ledger_consistent(db, uid)
        assert db.get(PlayerProfile, uid).vip_level == 0 and (db.get(PlayerProfile, uid).vip_xp or 0) == 0
        n_rewards = db.scalar(select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.user_id == uid, WalletTransaction.reason == "campaign_reward")) or 0
    # a retried task (same task key) replays its calls — a battle is never rewarded twice
    with session() as db:
        p = db.get(AiPersona, pid)
        PLAY.session(db, p, "T1", random.Random(1))
        rows = db.execute(select(WalletTransaction.ref, WalletTransaction.currency, func.count()).where(
            WalletTransaction.user_id == uid, WalletTransaction.reason == "campaign_reward")
            .group_by(WalletTransaction.ref, WalletTransaction.currency)).all()
        assert rows and all(n == 1 for _, _, n in rows)
        assert ledger_consistent(db, uid)
    # the same idempotency key on campaign completion replays the stored answer
    from app.core.security import CurrentUser
    from app.models import Battle
    from app.modules import game as GAME
    with session() as db:
        b = db.scalar(select(Battle).where(Battle.user_id == uid, Battle.status == "completed").limit(1))
        before = db.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == uid))
        r = GAME.campaign_complete(b.node_code, GAME.CompleteIn(battle_id=b.id), CurrentUser(uid, "t"), f"aiT1:c{b.node_code}", db)
        assert r.get("replayed") is True
        assert db.scalar(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.user_id == uid)) == before


def test_strategy_changes_after_campaign_losses(client):
    from app.ai import play as PLAY
    from app.models import AiPersona
    with session() as db:
        p = _ai(db, 1, 1002)[0]
        c = dict(p.counters or {})
        c["strategy"] = "balanced"
        p.counters = c
        node = type("N", (), {"order": 3, "name": "Тест", "code": "1-3"})()
        for _ in range(3):
            PLAY._after_battle(db, p, node, False, random.Random(1))
        assert p.counters["strategy"] == "defensive" and p.counters["camp_losses_row"] == 3
        slots = PLAY.best_formation(db, p, random.Random(2))
        assert any(slots)
        PLAY._after_battle(db, p, node, True, random.Random(1))
        assert db.get(AiPersona, p.id).counters["camp_losses_row"] == 0


def test_director_runs_play_tasks(client):
    from app.ai import settings as ST
    from app.ai.director import Director
    from app.core.db import utcnow
    from app.models import AiPersona, AiTask, PlayerProfile
    with session() as db:
        _ai(db, 6, 1003)
        real = db.scalar(select(PlayerProfile).where(PlayerProfile.is_ai.is_(False)))
        if real is not None:
            real.last_seen_at = utcnow()
        ST.update(db, {"mode": "normal", "sleep_when_empty": 0}, "test")
        for p in db.scalars(select(AiPersona)):
            p.session_until = utcnow() + timedelta(minutes=30)
        persona = db.scalar(select(AiPersona))
        from app.ai import tasks as TQ
        TQ.enqueue(db, "play", f"testplay:{persona.id}", persona_id=persona.id, priority=99)
    with session() as db:
        Director().tick(db)
        t = db.scalar(select(AiTask).where(AiTask.key == f"testplay:{persona.id}"))
        assert t.status == "done", (t.status, t.error)
        ST.update(db, {"mode": "test", "sleep_when_empty": 1}, "test")


def test_pvp_daily_limit_difficulty_rebuild_and_rankings_label(client, newplayer):
    from app.ai import compete as COMP
    from app.models import AiPersona, ArenaProfile
    with session() as db:
        ps = _ai(db, 6, 1004)
        p = ps[0]
        COMP.PVP.update(db, {"arena_fights_per_day": 2}, "test")
        assert COMP.arena_allowed(db, p) and COMP.arena_allowed(db, p) and not COMP.arena_allowed(db, p)
        me = db.get(ArenaProfile, p.user_id)
        cands = [db.get(ArenaProfile, x.user_id) for x in ps[1:]]
        COMP.PVP.update(db, {"difficulty": "easy"}, "test")
        easy = COMP.pick_opponent(db, p, me, cands, random.Random(1))
        COMP.PVP.update(db, {"difficulty": "challenging"}, "test")
        hard = COMP.pick_opponent(db, p, me, cands, random.Random(1))
        assert COMP.analyze(db, me, easy) >= COMP.analyze(db, me, hard)
        c = dict(p.counters or {})
        c["losses_row"] = 5
        p.counters = c
        assert COMP.maybe_rebuild_defense(db, p) is True
        COMP.PVP.update(db, {"arena_fights_per_day": 6, "difficulty": "fair", "ai_in_rankings": True}, "test")
    from app.social import rankings as RK
    RK._cache.clear()
    pl = newplayer()
    rows = pl.get("/rankings/power").json()["items"]
    ai_rows = [r for r in rows if r.get("is_ai")]
    assert ai_rows and all(r["rank"] is None for r in ai_rows)
    real_ranks = [r["rank"] for r in rows if not r.get("is_ai")]
    assert real_ranks == list(range(1, len(real_ranks) + 1))
    with session() as db:
        COMP.PVP.update(db, {"ai_in_rankings": False}, "test")
    RK._cache.clear()
    assert not any(r.get("is_ai") for r in pl.get("/rankings/power").json()["items"])


def test_event_ai_contribution_is_separate_and_capped(client):
    from app.ai import compete as COMP
    from app.core.db import utcnow
    from app.models import WorldEvent, WorldEventContribution
    from app.social import events as EVS
    with session() as db:
        ps = _ai(db, 3, 1005)
        for ev in db.scalars(select(WorldEvent).where(WorldEvent.status == "active")):
            ev.status = "finished"
        ev = WorldEvent(code="test:ai:" + ps[0].id[:6], template=next(iter(EVS.E()["templates"])), name="Тест",
                        kind="defense", status="active", starts_at=utcnow() - timedelta(hours=1),
                        ends_at=utcnow() + timedelta(hours=5), goal=1000, progress=0, ai_progress=0, choice_votes={})
        db.add(ev)
        db.flush()
        eid = ev.id
        COMP.EVENTS.update(db, {"points_per_action": 150}, "test")
        for _ in range(10):
            for p in ps:
                COMP.contribute_event(db, p)
        db.flush()
        db.refresh(ev)
        assert ev.ai_progress == 200 and ev.progress == 0  # 20% of the goal, separate line
        assert db.query(WorldEventContribution).filter(WorldEventContribution.event_id == eid).count() == 0  # no tops/rewards
        ev.progress = 800
        db.flush()
        EVS.finish(db, ev)
        assert ev.outcome == "success"  # the AI line counts towards the goal


def test_admin_game_card_wallet_heroes_strategy_play_and_economy(client):
    from app.models import WalletTransaction
    with session() as db:
        p = _ai(db, 1, 1006)[0]
        pid, uid = p.id, p.user_id
    g = client.get(f"/admin/api/ai/characters/{pid}/game", headers=AH()).json()
    assert g["heroes"] and "wallet" in g and g["economy"] in g["economies"]
    assert client.post(f"/admin/api/ai/characters/{pid}/wallet", headers=AH(), json={"currency": "gold", "delta": 5000}).status_code == 200
    assert client.post(f"/admin/api/ai/characters/{pid}/wallet", headers=AH(), json={"currency": "bitcoin", "delta": 1}).status_code == 400
    with session() as db:
        assert db.scalar(select(WalletTransaction).where(WalletTransaction.user_id == uid, WalletTransaction.reason == "admin_ai"))
    h = g["heroes"][0]
    assert client.patch(f"/admin/api/ai/characters/{pid}/heroes/{h['id']}", headers=AH(), json={"level": h["level"] + 1}).status_code == 200
    owned = {x["code"] for x in g["heroes"]}
    new = next(x for x in g["summonable"] if x["code"] not in owned)
    assert client.post(f"/admin/api/ai/characters/{pid}/heroes", headers=AH(), json={"hero_code": new["code"]}).status_code == 200
    assert client.post(f"/admin/api/ai/characters/{pid}/heroes", headers=AH(), json={"hero_code": new["code"]}).status_code == 409
    assert client.post(f"/admin/api/ai/characters/{pid}/strategy", headers=AH(), json={"strategy": "aggressive", "economy": "saver"}).json()["economy"] == "saver"
    assert client.post(f"/admin/api/ai/characters/{pid}/rebuild", headers=AH()).status_code == 200
    assert client.post(f"/admin/api/ai/characters/{pid}/play", headers=AH()).json()["task_id"]
    e = client.get("/admin/api/ai/economy", headers=AH()).json()
    assert "balances" in e and "flows_24h" in e
    for sec in ("play", "pvp", "events"):
        assert client.get(f"/admin/api/ai/settings/{sec}", headers=AH()).status_code == 200
    assert client.post("/admin/api/ai/settings/events", headers=AH(), json={"share_pct": 50}).status_code == 400  # D-05: ≤ 20%


def test_ai_guild_weekly_contest_once(client):
    from app.ai import compete as COMP
    from app.ai import guild_ai as GAI
    from app.models import ChatMessage, GuildMember
    with session() as db:
        _ai(db, 10, 1007)
        g = GAI.found_guild(db, random.Random(9), {**GAI.SECTION.get(db), "max_ai_guilds": 50, "found_min_free": 6})
        for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == g.id)):
            m.contribution_week = random.randint(1, 50)
        assert COMP.guild_contest(db, g, random.Random(1)) is not None
        assert COMP.guild_contest(db, g, random.Random(1)) is None  # once a week
        db.flush()
        msgs = [m.text for m in db.scalars(select(ChatMessage).where(ChatMessage.channel == f"guild:{g.id}"))]
        assert any("Соревнование недели" in t for t in msgs), msgs
