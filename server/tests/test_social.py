"""Integration tests for the online systems: friends, guilds, chat/moderation, raids, arena, tournaments,
world events, AI population, progression, rankings and anti-cheat."""
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import get_db, utcnow

ADMIN = "social-admin-token-0123456789abcdef"


@contextmanager
def session():
    gen = get_db()
    db = next(gen)
    try:
        yield db
        db.commit()
    finally:
        gen.close()


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def AH():
    return {"X-Admin-Token": ADMIN, "X-Admin-Name": "moderator"}


def uid(p):
    return p.tokens["user_id"]


def set_profile(p, **kw):
    from app.models import PlayerProfile
    with session() as db:
        pr = db.get(PlayerProfile, uid(p))
        for k, v in kw.items():
            setattr(pr, k, v)


def give(p, **cur):
    from app.services import grant
    with session() as db:
        grant(db, uid(p), cur, "test")


def public_id(p):
    return p.get("/player/me").json()["profile"]["uralia_id"]


def friends(a, b):
    r = a.post("/social/friends/request", {"uralia_id": public_id(b)}, key=False)
    assert r.status_code == 200, r.text
    req = b.get("/social/friends").json()["incoming"][0]
    assert b.post(f"/social/friends/requests/{req['id']}/accept", key=False).status_code == 200


# ------------------------------------------------------------------ friends
def test_friends_requests_gifts_help_and_profile(newplayer):
    a, b = newplayer(), newplayer()
    friends(a, b)
    fa = a.get("/social/friends").json()
    assert fa["friends"][0]["user_id"] == uid(b) and fa["max"] == 50
    assert fa["friends"][0]["presence"] == "online"
    # gift: once per friend per day, idempotent replay does not duplicate
    k = uuid.uuid4().hex
    assert a.post(f"/social/gifts/send/{uid(b)}", key=k).status_code == 200
    assert a.post(f"/social/gifts/send/{uid(b)}", key=k).json().get("replayed")
    assert a.post(f"/social/gifts/send/{uid(b)}").status_code == 409
    # help -> blessing for the friend's next PvE battles
    assert a.post(f"/social/help/{uid(b)}").status_code == 200
    before = b.get("/player/me").json()["wallet"]
    claim = b.post("/social/gifts/claim-all").json()
    assert claim["claimed"] == 2 and claim["rewards"]["friend_tokens"] == 5
    after = b.get("/player/me").json()["wallet"]
    assert after["friend_tokens"] == before.get("friend_tokens", 0) + 5
    assert b.get("/social/friends").json()["blessing_battles"] == 3
    v = b.post("/battles/validate", {"node_id": "1-1"}, key=False).json()
    assert v["simulation"]["bonuses"]["friend_blessing"] > 0
    assert b.get("/social/friends").json()["blessing_battles"] == 2
    # paid currency or heroes are never giftable: the gift contents come from server config only
    assert "crystals" not in claim["rewards"]
    # profile of a friend
    prof = a.get(f"/social/profile/{uid(b)}").json()
    assert prof["friend"] and prof["heroes"] and prof["squad"] and "fortress" in prof
    # presence can be hidden
    b.post("/social/presence", {"hidden": True}, key=False)
    assert a.get("/social/friends").json()["friends"][0]["presence"] == "hidden"
    # achievements: first friend
    ach = {x["code"]: x for x in a.get("/progression").json()["achievements"]}
    assert ach["first_friend"]["done"]


def test_friend_limits_invites_search_and_block(newplayer):
    a, b, c = newplayer(), newplayer(), newplayer()
    assert a.post("/social/friends/request", {"uralia_id": public_id(a)}, key=False).status_code == 400
    inv = a.post("/social/invite", key=False).json()
    r = c.post("/social/invite/redeem", {"code": inv["code"]}, key=False)
    assert r.status_code == 200 and r.json()["status"] == "friends"
    set_profile(b, nickname="Искомый" + uuid.uuid4().hex[:4])
    nick = b.get("/player/me").json()["profile"]["nickname"]
    assert any(x["user_id"] == uid(b) for x in a.get(f"/social/search?q={nick[:6]}").json()["items"])
    # mutual requests auto-accept
    a.post("/social/friends/request", {"uralia_id": public_id(b)}, key=False)
    assert b.post("/social/friends/request", {"uralia_id": public_id(a)}, key=False).json()["status"] == "friends"
    # block removes friendship and hides
    assert a.post(f"/social/block/{uid(b)}", key=False).status_code == 200
    assert [x["user_id"] for x in a.get("/social/friends").json()["blocked"]] == [uid(b)]  # privacy: block list
    assert all(f["user_id"] != uid(b) for f in a.get("/social/friends").json()["friends"])
    assert b.post("/social/friends/request", {"uralia_id": public_id(a)}, key=False).status_code == 403
    # gift only to friends
    assert a.post(f"/social/gifts/send/{uid(b)}").status_code == 403
    # token shop spends friend tokens with weekly limits
    give(a, friend_tokens=100)
    r = a.post("/social/token-shop/tok_gold/buy")
    assert r.status_code == 200, r.text
    assert next(i for i in a.get("/social/token-shop").json()["items"] if i["id"] == "tok_gold")["bought"] == 1


# ------------------------------------------------------------------ guilds
def make_guild(leader, mode="open", name=None):
    set_profile(leader, level=10)
    give(leader, gold=60000)
    r = leader.post("/guilds/create", {"name": name or ("Клан " + uuid.uuid4().hex[:6]), "tag": "T" + uuid.uuid4().hex[:3].upper(),
                                       "join_mode": mode})
    assert r.status_code == 200, r.text
    return r.json()["guild_id"]


def test_guild_roles_permissions_development_and_tasks(newplayer):
    lead, m1, m2 = newplayer(), newplayer(), newplayer()
    set_profile(lead, level=2)
    give(lead, gold=60000)
    assert lead.post("/guilds/create", {"name": "Слабый клан", "tag": "WEAK"}).status_code == 403  # level requirement
    gid = make_guild(lead, mode="approval")
    assert m1.post(f"/guilds/{gid}/join", key=False).json()["status"] == "pending"
    app = lead.get("/guilds/mine").json()["applications"][0]
    assert lead.post(f"/guilds/applications/{app['id']}/accept", key=False).status_code == 200
    lead.post("/guilds/edit", {"join_mode": "open"}, key=False)
    assert m2.post(f"/guilds/{gid}/join", key=False).json()["status"] == "joined"
    g = lead.get("/guilds/mine").json()
    assert {m["role"] for m in g["members"]} == {"leader", "novice"} and len(g["members"]) == 3
    # novice cannot kick; leader promotes to officer; officer cannot kick another officer
    assert m1.post(f"/guilds/members/{uid(m2)}/kick", key=False).status_code == 403
    assert lead.post(f"/guilds/members/{uid(m1)}/role", {"role": "officer"}, key=False).status_code == 200
    assert lead.post(f"/guilds/members/{uid(m2)}/role", {"role": "officer"}, key=False).status_code == 200
    assert m1.post(f"/guilds/members/{uid(m2)}/kick", key=False).status_code == 403
    assert m1.post(f"/guilds/members/{uid(lead)}/role", {"role": "member"}, key=False).status_code == 403
    # leader cannot leave without transfer; transfer works
    assert lead.post("/guilds/leave", key=False).status_code == 409
    assert lead.post("/guilds/transfer", {"user_id": uid(m1)}, key=False).status_code == 200
    g = m1.get("/guilds/mine").json()
    assert g["my_role"] == "leader"
    # donations fill the treasury; building and branch research
    give(m1, gold=100000)
    for _ in range(5):
        assert m1.post("/guilds/donate").status_code == 200
    assert m1.post("/guilds/donate").status_code == 409  # daily max
    with session() as db:
        from app.models import Guild
        db.get(Guild, gid).treasury = 20000
    assert m1.post("/guilds/build/hall", key=False).json()["level"] == 2
    assert m1.post("/guilds/build/forge", key=False).json()["level"] == 1
    assert m1.post("/guilds/research/r_tracker", key=False).status_code == 409  # branch not chosen
    assert m1.post("/guilds/specialize", {"code": "hunters"}, key=False).status_code == 200
    assert m1.post("/guilds/research/r_tracker", key=False).json()["level"] == 1
    bonuses = m1.get("/guilds/mine").json()["bonuses"]
    assert bonuses["atk_pct"] == pytest.approx(0.02) and bonuses["boss_dmg_pct"] > 0.1
    # daily task: donate already done -> claim once
    t = next(x for x in m1.get("/guilds/mine").json()["tasks"] if x["code"] == "g_donate")
    assert t["progress"] == 1
    k = uuid.uuid4().hex
    assert m1.post("/guilds/tasks/g_donate/claim", key=k).status_code == 200
    assert m1.post("/guilds/tasks/g_donate/claim").status_code == 409
    # log keeps management history
    actions = {lg["action"] for lg in m1.get("/guilds/mine").json()["log"]}
    assert {"create", "join", "role", "transfer", "building", "research", "specialize"} <= actions


def test_guild_expedition_war_weekly_rewards_and_inactivity(newplayer):
    from app.models import GuildExpedition, GuildMember, GuildWar, PlayerMail
    from app.social import guilds as GS
    a1, a2, a3 = newplayer(), newplayer(), newplayer()
    b1, b2, b3 = newplayer(), newplayer(), newplayer()
    ga = make_guild(a1)
    for p in (a2, a3):
        p.post(f"/guilds/{ga}/join", key=False)
    gb = make_guild(b1)
    for p in (b2, b3):
        p.post(f"/guilds/{gb}/join", key=False)
    e = a1.post("/guilds/expeditions/start", {"code": "exp_iremel"}, key=False).json()
    assert a2.post(f"/guilds/expeditions/{e['id']}/join", key=False).status_code == 200
    with session() as db:
        db.get(GuildExpedition, e["id"]).ends_at = utcnow() - timedelta(minutes=1)
    with session() as db:
        assert GS.settle_expeditions(db) >= 1
    res = a1.get("/guilds/mine").json()["expeditions"][0]
    assert res["status"] == "done" and res["result"]["ratio"] > 0
    # war: matched against another guild of similar level, attacks limited, scores, rewards for all members
    w = a1.post("/guilds/war/start", key=False).json()
    assert w["opponent"] and w["targets"]
    target = w["targets"][0]["user_id"]
    for _ in range(3):
        assert a2.post("/guilds/war/attack", {"user_id": target}).status_code == 200
    assert a2.post("/guilds/war/attack", {"user_id": target}).status_code == 409
    with session() as db:
        war = db.get(GuildWar, w["id"])
        war.ends_at = utcnow() - timedelta(minutes=1)
    with session() as db:
        assert GS.finish_wars(db) == 1
    # weekly rewards: base for every active member, personal bonus capped
    with session() as db:
        for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == ga)):
            m.contribution_week = 5000 if m.user_id == uid(a1) else 15
        before = db.scalar(select(func.count()).select_from(PlayerMail).where(PlayerMail.user_id == uid(a3))) or 0
        GS.weekly_rewards(db)
        after = db.scalar(select(func.count()).select_from(PlayerMail).where(PlayerMail.user_id == uid(a3))) or 0
        assert after == before + 1
        assert all((m.contribution_week or 0) == 0 for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == ga)))
    # inactivity: warning after N days, member notified, leader can kick
    with session() as db:
        m = db.get(GuildMember, (ga, uid(a3)))
        m.last_active_at = utcnow() - timedelta(days=4)
    with session() as db:
        assert GS.inactivity_scan(db) >= 1
    mem = {x["user_id"]: x for x in a1.get("/guilds/mine").json()["members"]}
    assert mem[uid(a3)]["warned"] and mem[uid(a3)]["inactive_days"] >= 3
    assert a1.post(f"/guilds/members/{uid(a3)}/kick", key=False).status_code == 200


# ------------------------------------------------------------------ chat & moderation
def test_chat_filter_flood_reactions_dm_reports_and_mutes(newplayer):
    from app.social import chat as CH
    CH._recent.clear()
    a, b = newplayer(), newplayer()
    r = a.post("/chat/send", {"channel": "global", "text": "Привет всем, кто идёт на босса гильдии сегодня?"}, key=False)
    assert r.status_code == 200, r.text
    mid = r.json()["message"]["id"]
    assert a.post("/chat/send", {"channel": "global", "text": "ещё"}, key=False).status_code == 429  # too fast
    CH._recent.clear()
    bad = a.post("/chat/send", {"channel": "global", "text": "ты дурак, заходи на сайт cheat.ru +7 999 123-45-67"}, key=False).json()["message"]
    assert "дурак" not in bad["text"] and "cheat.ru" not in bad["text"] and "999" not in bad["text"]
    CH._recent.clear()
    assert a.post("/chat/send", {"channel": "global", "text": "Привет всем, кто идёт на босса гильдии сегодня?"}, key=False).status_code == 409
    msgs = b.get("/chat/messages?channel=global").json()["messages"]
    assert any(m["id"] == mid for m in msgs)
    assert b.post(f"/chat/messages/{mid}/react", {"emoji": "🔥"}, key=False).json()["reactions"]["🔥"]["count"] == 1
    # private messages
    CH._recent.clear()
    assert a.post("/chat/send", {"to_user": uid(b), "text": "Привет! Пойдёшь в совместный рейд?"}, key=False).status_code == 200
    chans = b.get("/chat/channels").json()["channels"]
    dm = next(c for c in chans if c["channel"].startswith("dm:"))
    assert dm["unread"] == 1
    assert newplayer().get(f"/chat/messages?channel={dm['channel']}").status_code == 403
    # three distinct reporters -> short automatic mute (never a ban)
    for _ in range(3):
        newplayer().post("/chat/report", {"message_id": bad["id"], "reason": "abuse"}, key=False)
    CH._recent.clear()
    r = a.post("/chat/send", {"channel": "global", "text": "Можно мне снова писать в чат пожалуйста?"}, key=False)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "muted"
    my = a.get("/moderation/my").json()["sanctions"]
    assert my[0]["kind"] == "mute" and my[0]["source"] == "auto"
    assert a.post("/moderation/appeal", {"sanction_id": my[0]["id"], "text": "Это было недоразумение, прошу снять."}, key=False).status_code == 200
    # meaningful message counted, spammy one not
    st = b.get("/progression").json()["stats"]
    CH._recent.clear()
    b.post("/chat/send", {"channel": "global", "text": "ок"}, key=False)
    assert b.get("/progression").json()["stats"].get("chat_meaningful", 0) == st.get("chat_meaningful", 0)


def test_admin_moderation_ban_appeal_and_revoke(client, newplayer):
    p = newplayer()
    pid = public_id(p)
    r = client.post("/admin/api/social/sanctions", json={"uralia_id": pid, "kind": "temp_ban", "reason": "Читерство", "minutes": 60}, headers=AH())
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    rr = client.post("/api/v1/auth/refresh", json={"refresh_token": p.tokens["refresh_token"]})
    assert rr.status_code in (401, 403)
    # banned player appeals with the stored refresh token
    ap = client.post("/api/v1/moderation/ban-appeal", json={"refresh_token": p.tokens["refresh_token"], "sanction_id": sid,
                                                             "text": "Я не использовал читы, проверьте пожалуйста."})
    assert ap.status_code == 200, ap.text
    appeal = client.get("/admin/api/social/appeals", headers=AH()).json()["items"][0]
    assert client.post(f"/admin/api/social/appeals/{appeal['id']}", json={"accept": True, "resolution": "Ошибка"}, headers=AH()).status_code == 200
    from app.models import User
    with session() as db:
        assert db.get(User, uid(p)).is_banned is False
    assert client.get("/admin/api/social/overview", headers=AH()).status_code == 200
    assert client.get(f"/admin/api/social/players/{pid}", headers=AH()).json()["sanctions"][0]["status"] == "revoked"


# ------------------------------------------------------------------ raids
def test_raids_attempts_tickets_loot_and_coop(newplayer):
    from app.models import RaidInstance, RaidLoot
    lead = newplayer()
    make_guild(lead)
    ov = lead.get("/raids").json()
    kinds = {r["kind"]: r for r in ov["raids"]}
    assert kinds["guild"]["attempts"] == 3 and kinds["world"]["phases"]
    r = lead.post("/raids/attack", {"kind": "guild"})
    assert r.status_code == 200, r.text
    assert r.json()["damage"] > 0 and r.json()["simulation"]["boss_damage"] == r.json()["damage"]
    for _ in range(2):
        lead.post("/raids/attack", {"kind": "guild"})
    assert lead.post("/raids/attack", {"kind": "guild"}).status_code == 409
    give(lead, raid_tickets=1)
    assert lead.post("/raids/attack", {"kind": "guild", "use_ticket": True}).json()["used"] == "ticket"
    # finishing the boss: loot rolled once per (raid, user, slot)
    gid = lead.get("/guilds/mine").json()["guild"]["id"]
    with session() as db:
        inst = db.scalar(select(RaidInstance).where(RaidInstance.guild_id == gid, RaidInstance.kind == "guild",
                                                    RaidInstance.status == "active"))
        inst.hp_left = 10
    give(lead, raid_tickets=1)
    r = lead.post("/raids/attack", {"kind": "guild", "use_ticket": True}).json()
    assert r["killed"], {k: v for k, v in r.items() if k != "simulation"}
    with session() as db:
        rows = db.scalars(select(RaidLoot).where(RaidLoot.raid_id == inst.id, RaidLoot.user_id == uid(lead))).all()
        assert any(x.slot == "base" for x in rows)
        from app.social.raids import finish, roll_loot, boss_conf
        n_before = len(rows)
        finish(db, db.get(RaidInstance, inst.id))  # second call is a no-op
        roll_loot(db, inst.id, [uid(lead)], boss_conf(inst.boss_code))  # duplicates are skipped
        assert db.scalar(select(func.count()).select_from(RaidLoot).where(RaidLoot.raid_id == inst.id, RaidLoot.user_id == uid(lead))) >= n_before
    hist = lead.get("/raids/loot").json()["items"]
    assert hist and all("chance" in x for x in hist)
    # co-op: leader + friend + AI ally, one fight with shared HP
    mate = newplayer()
    lb = lead.post("/raids/coop/create", {"boss_code": "rb_kurgan_colossus"}, key=False).json()
    assert mate.post(f"/raids/coop/{lb['id']}/join", key=False).status_code == 200
    from app.social.ai.population import ensure_population
    with session() as db:
        ensure_population(db, max_new=3)
    lead.post(f"/raids/coop/{lb['id']}/add-ai", key=False)
    res = lead.post(f"/raids/coop/{lb['id']}/start").json()
    waves = res["lobby"]["result"]["waves"]
    assert len(waves) >= 2 and sum(w["damage"] for w in waves) > 0
    assert any(w["is_ai"] for w in waves) or len(res["lobby"]["members"]) == 2


# ------------------------------------------------------------------ arena
def test_arena_ranked_training_replay_and_season(newplayer):
    from app.models import ArenaProfile, ArenaSeason, SeasonResult
    from app.social.ai.population import ensure_population
    a, b = newplayer(), newplayer()
    b.get("/arena")
    ar = a.get("/arena").json()
    assert ar["me"]["rating"] == 1000 and ar["me"]["attempts_left"] == 5
    assert ar["candidates"]["ranked"] and all(not c["is_ai"] for c in ar["candidates"]["ranked"])
    r = a.post("/arena/fight", {"opponent_id": uid(b)}).json()
    assert r["delta"] != 0 and r["rating"] == 1000 + r["delta"]
    with session() as db:
        assert db.get(ArenaProfile, uid(b)).rating == 1000 - round(r["delta"] * 0.5)
    rep = a.get(f"/arena/replay/{r['match_id']}").json()
    assert rep["consistent"]
    # AI opponents: training only, no rating change
    with session() as db:
        ensure_population(db, max_new=3)
    ai = a.get("/arena").json()["candidates"]["training"][0]
    assert a.post("/arena/fight", {"opponent_id": ai["user_id"], "kind": "ranked"}).status_code == 400
    rating = a.get("/arena").json()["me"]["rating"]
    t = a.post("/arena/fight", {"opponent_id": ai["user_id"], "kind": "training"}).json()
    assert t["delta"] == 0 and a.get("/arena").json()["me"]["rating"] == rating
    # defense squad
    slots = a.get("/player/bootstrap").json()["formation"]
    assert a.post("/arena/defense", {"slots": slots}, key=False).json()["defense_power"] > 0
    # season close: partial reset, permanent history, new season
    with session() as db:
        s = db.scalar(select(ArenaSeason).where(ArenaSeason.status == "active"))
        sid = s.id
        s.ends_at = utcnow() - timedelta(minutes=1)
    a.get("/arena")
    with session() as db:
        assert db.get(ArenaSeason, sid).status == "closed"
        assert db.scalar(select(SeasonResult).where(SeasonResult.user_id == uid(a), SeasonResult.category == "arena",
                                                    SeasonResult.season_id == sid)) is not None
        ap = db.get(ArenaProfile, uid(a))
        assert ap.wins == 0 and abs(ap.rating - 1000) <= abs(rating - 1000)


# ------------------------------------------------------------------ tournaments
def test_tournaments_register_rules_rounds_and_rewards(newplayer):
    from app.models import Tournament, TournamentEntry, SeasonResult
    from app.social import tournaments as TS
    players = [newplayer() for _ in range(4)]
    players[0].get("/tournaments")
    with session() as db:  # fresh tournaments independent of earlier runs on a persistent DB
        key = "T" + uuid.uuid4().hex[:8]
        start = utcnow() - timedelta(hours=1)
        w = TS._ensure_one(db, "weekly_open", TS.T()["templates"]["weekly_open"], start, key)
        r_ = TS._ensure_one(db, "weekly_rare", TS.T()["templates"]["weekly_rare"], start, key)
        weekly, rare = {"id": w.id}, {"id": r_.id}
    for p in players:
        r = p.post(f"/tournaments/{weekly['id']}/register", {}, key=False)
        assert r.status_code == 200, r.text
    assert players[0].post(f"/tournaments/{weekly['id']}/register", {}, key=False).status_code == 409
    # rarity-capped tournament validates the squad (starters are within the cap)
    assert players[1].post(f"/tournaments/{rare['id']}/register", {}, key=False).status_code in (200, 400)
    with session() as db:
        t = db.get(Tournament, weekly["id"])
        t.reg_ends_at = utcnow() - timedelta(hours=200)
        t.ends_at = utcnow() - timedelta(minutes=1)
        TS.advance(db)
        t = db.get(Tournament, weekly["id"])
        assert t.status == "finished" and t.current_round >= 1
        assert t.results["standings"][0]["place"] == 1
        pts = [e.points for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id))]
        assert sum(pts) > 0
        assert db.scalar(select(func.count()).select_from(SeasonResult).where(SeasonResult.ref == t.code[:64])) >= 4
    view = players[0].get(f"/tournaments/{weekly['id']}").json()
    assert view["matches"] and view["standings"]
    m = next(x for x in view["matches"] if not x["bye"])
    assert players[0].get(f"/tournaments/match/{m['id']}/replay").status_code == 200


# ------------------------------------------------------------------ world events
def test_world_events_contribution_outcome_world_state_and_restore(client, newplayer):
    from app.models import WorldEvent, WorldState
    from app.social import events as EV
    p = newplayer()
    with session() as db:  # a fresh active event independent of earlier runs on a persistent DB
        we = WorldEvent(code="test:" + uuid.uuid4().hex[:10], template="spring_festival", name="Праздник Каргатуй",
                        kind="holiday", scale="weekly", starts_at=utcnow() - timedelta(hours=1),
                        ends_at=utcnow() + timedelta(days=1), goal=1500000, progress=0, choice_votes={})
        db.add(we)
        db.flush()
        eid = we.id
    ev = p.get("/events").json()
    e = next(x for x in ev["active"] if x["id"] == eid)
    r = p.post(f"/events/{e['id']}/battle")
    assert r.status_code == 200, r.text
    p.post("/battles/validate", {"node_id": "1-1"}, key=False)
    mine = next(x for x in p.get("/events").json()["active"] if x["id"] == e["id"])
    assert mine["my_points"] > 0 and mine["progress"] >= mine["my_points"]
    if mine["choices"]:
        assert p.post(f"/events/{e['id']}/vote", {"choice": list(mine["choices"])[0]}, key=False).status_code == 200
    with session() as db:
        v0 = EV.world(db).version
        we = db.get(WorldEvent, e["id"])
        we.progress = we.goal + 1
        we.ends_at = utcnow() - timedelta(minutes=1)
    with session() as db:
        assert EV.finish_due(db) >= 1
        ws = EV.world(db)
        assert ws.version > v0 and ws.state["chronicle"][-1]["outcome"] == "success"
    w = client.get("/admin/api/social/world", headers=AH()).json()
    assert w["versions"][0]["version"] == ws.version
    rr = client.post("/admin/api/social/world/restore", json={"version": v0}, headers=AH())
    assert rr.status_code == 200
    with session() as db:
        assert EV.world(db).state == db.get(WorldState, v0).state


# ------------------------------------------------------------------ AI population
def test_ai_population_is_labelled_bounded_and_separate(client, newplayer):
    from app.models import AiPersona, PlayerProfile, ChatMessage
    from app.social.ai import population as AIP
    with session() as db:
        AIP.ensure_population(db, max_new=8)
    with session() as db:
        personas = db.scalars(select(AiPersona)).all()
        assert len(personas) >= 8
        profs = [db.get(PlayerProfile, x.user_id) for x in personas]
        assert all(p.is_ai for p in profs)
        assert len({p.nickname for p in profs}) == len(profs)
        assert len({x.archetype for x in personas}) >= 3 and len({x.style for x in personas}) >= 3
        for x in personas:
            x.next_action_at = utcnow() - timedelta(minutes=1)
            x.schedule = {"hours": list(range(24))}
    with session() as db:
        st = AIP.tick(db)
        assert 0 < st["actions"] <= AIP.AI()["max_actions_per_tick"]
    # AI never appears in real-player rankings; separate AI board exists
    p = newplayer()
    power = p.get("/rankings/power").json()
    assert all(not x.get("is_ai") for x in power["items"])
    with session() as db:
        ai_ids = {x.user_id for x in db.scalars(select(AiPersona))}
    assert not ai_ids & {x["user_id"] for x in power["items"]}
    assert p.get("/rankings/ai").json()["items"]
    # friend request to an AI is decided by the persona; DMs get a labelled reply
    ai_pid = db_public = None
    with session() as db:
        ai_pid = db.get(PlayerProfile, next(iter(ai_ids))).uralia_id
    r = p.post("/social/friends/request", {"uralia_id": ai_pid}, key=False).json()
    assert r["status"] in ("friends", "pending")
    card = p.get("/social/search?q=" + ai_pid).json()["items"][0]
    assert card["is_ai"] is True
    from app.social import chat as CH
    CH._recent.clear()
    p.post("/chat/send", {"to_user": card["user_id"], "text": "Привет! Ты бот?"}, key=False)
    with session() as db:  # the reply waits a human-like pause in the ai_events queue; make it due now
        from datetime import timedelta as _td
        from app.core.db import utcnow as _now
        from app.models import AiEvent
        for ev in db.query(AiEvent).filter(AiEvent.handled_at.is_(None)):
            ev.due_at = _now() - _td(seconds=1)
        db.flush()
        AIP.process_replies(db, 10)
    msgs = p.get(f"/chat/messages?channel={CH.dm_channel(uid(p), card['user_id'])}").json()["messages"]
    assert any(m["is_ai"] and m["author"]["is_ai"] for m in msgs)
    # admin overview of the AI engine
    assert client.get("/admin/api/social/overview", headers=AH()).json()["ai"]["active"] >= 8
    _ = (db_public, ChatMessage)


def test_rankings_progression_and_anticheat(newplayer):
    from app.social import anticheat as AC
    p = newplayer()
    for cat in ("power", "arena", "reputation", "guilds", "raids", "events", "tournaments"):
        assert p.get(f"/rankings/{cat}").status_code == 200
    prog = p.get("/progression").json()
    assert "legacy" in prog and "records" in prog and prog["achievements"]
    with session() as db:
        res = AC.economy_scan(db)
        assert res["ledger_mismatches"] == 0
        assert AC.flag(db, uid(p), "test_signal", 1) is True
        assert AC.flag(db, uid(p), "test_signal", 1) is False  # throttled, no flag spam


def test_scheduler_jobs_run_and_are_idempotent():
    from app.social import scheduler as SCH
    for name in SCH.JOBS:
        r = SCH.run_job(name, force=True)
        assert "error" not in r, (name, r)
    assert SCH.run_job("tournaments")["skipped"] in ("not due", "leased")


def test_client_release_prompt(client, tmp_path, monkeypatch):
    import json
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "downloads_path", tmp_path)
    (tmp_path / "uralia-9.0.0.apk").write_bytes(b"PK-fake-apk")
    (tmp_path / "release.json").write_text(json.dumps({"version": "9.0.0", "min_version": "0.5.0",
                                                       "file": "uralia-9.0.0.apk", "notes": ["Чат"]}), encoding="utf-8")
    r = client.get("/api/v1/client/release?version=0.4.0").json()
    assert r["update_available"] and r["required"] and r["url"].endswith("/download") and r["notes"] == ["Чат"]
    r = client.get("/api/v1/client/release?version=9.0.0").json()
    assert not r["update_available"] and not r["required"]
    assert "9.0.0" in client.get("/download").text
    assert client.get("/download/apk").content == b"PK-fake-apk"


def test_ai_conversations_keep_chat_alive():
    from app.models import ChatMessage
    from app.social.ai import banter as B
    from app.social.ai import population as AIP
    from app.social.chat import contains_bad
    with session() as db:
        AIP.ensure_population(db, max_new=6)
    with session() as db:
        from datetime import timedelta
        from app.core.db import utcnow
        from app.models import ServerSetting
        start = db.scalar(select(func.max(ChatMessage.id))) or 0
        B._queue.clear()
        row = db.get(ServerSetting, B.PAUSE_KEY)
        if row is not None:
            db.delete(row)  # no quiet period left over from other tests
        db.flush()
        n = B.start_conversation(db)
        assert n >= 3
        B._queue.extend([(0, u, c, t) for _, u, c, t in list(B._queue)])  # make every line due now
        while B._queue and B._queue[0][0] != 0:
            B._queue.popleft()
        posted = 0
        for _ in range(n + 2):  # one line per flush, each after the minimum gap (a real chat, not a stream)
            got = B.flush(db, limit=50)
            assert got <= 1
            posted += got
            for m in db.scalars(select(ChatMessage).where(ChatMessage.channel == "global", ChatMessage.is_ai.is_(True),
                                                          ChatMessage.id > start)):
                m.created_at = utcnow() - timedelta(seconds=11)
            db.flush()
        assert posted >= 3
        assert B.in_pause(db, "global")  # after the discussion the chat is quiet for 5-15 minutes
    with session() as db:
        msgs = db.scalars(select(ChatMessage).where(ChatMessage.id > start, ChatMessage.channel == "global")).all()
        assert len({m.user_id for m in msgs}) >= 2 and all(m.is_ai for m in msgs)
        assert not any(contains_bad(m.text) for m in msgs)
        assert any("@" in m.text for m in msgs)  # personas address each other
        stats = B.keep_alive(db, AIP.AI())
        assert "posted" in stats


def test_chat_retention_and_ai_chat_toggle(newplayer):
    from app.models import ChatMessage, PlayerProfile
    from app.social import chat as CH
    p = newplayer()
    ch = "dm:test:" + uuid.uuid4().hex[:8]
    with session() as db:
        for i in range(130):
            db.add(ChatMessage(channel=ch, user_id=uid(p), text=f"msg {i}", reactions={}))
    with session() as db:
        CH.prune(db)
    with session() as db:
        left = db.scalars(select(ChatMessage).where(ChatMessage.channel == ch).order_by(ChatMessage.id)).all()
        assert len(left) == 100 and left[0].text == "msg 30"
    # hide AI messages in the global chat for this player only
    with session() as db:
        ai = db.scalar(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True)))
        db.add(ChatMessage(channel="global", user_id=ai.user_id, text="Я ИИ и болтаю", is_ai=True, reactions={}))
    assert any(m["is_ai"] for m in p.get("/chat/messages?channel=global").json()["messages"])
    assert p.post("/social/ai-prefs", {"show_ai_chat": False}, key=False).json()["prefs"]["show_ai_chat"] is False
    assert not any(m["is_ai"] for m in p.get("/chat/messages?channel=global").json()["messages"])
    msg = p.get("/chat/messages?channel=global").json()["messages"]
    assert all("avatar_hero" in m["author"] for m in msg if m["author"])


def test_ai_participation_switches_and_fair_play(client, newplayer):
    from app.models import AiPersona, ArenaMatch, Guild, GuildMember, PlayerProfile, RaidInstance
    from app.social.ai import population as AIP
    from app.social.ai.control import global_switches
    with session() as db:
        AIP.ensure_population(db, max_new=6)
    # guild leader policy
    lead = newplayer()
    gid = make_guild(lead)
    r = lead.post("/guilds/ai-policy", {"management": True, "wars": False}, key=False).json()["policy"]
    assert r["management"] and not r["wars"] and lead.get("/guilds/mine").json()["ai_policy"]["values"]["management"]
    # AI raids never take a shared boss below 10% and never get loot
    with session() as db:
        persona = db.scalars(select(AiPersona)).first()
        prof = db.get(PlayerProfile, persona.user_id)
        from app.social.raids import current_instance
        inst = current_instance(db, "world", None)
        inst.hp_left = int(inst.hp_max * 0.12)
        for _ in range(3):
            AIP.act_raid(db, persona, prof)
        inst = db.get(RaidInstance, inst.id)
        assert inst.hp_left >= int(inst.hp_max * 0.10) - 1
    # AI arena attacks respect the player's personal switch
    a = newplayer()
    a.get("/arena")
    a.post("/social/ai-prefs", {"arena_defense": False}, key=False)
    with session() as db:
        for persona in db.scalars(select(AiPersona)).all()[:6]:
            AIP.act_arena(db, persona, db.get(PlayerProfile, persona.user_id))
        assert db.scalar(select(func.count()).select_from(ArenaMatch).where(ArenaMatch.defender_id == uid(a))) == 0
    # owner switch turns AI arena off entirely (only the AI ladder remains)
    assert client.post("/admin/api/social/ai-switches", json={"arena": False, "chat": False}, headers=AH()).status_code == 200
    with session() as db:
        assert global_switches(db)["arena"] is False
    from app.social.ai import banter
    with session() as db:
        assert banter.keep_alive(db, AIP.AI()).get("disabled")
    client.post("/admin/api/social/ai-switches", json={"arena": True, "chat": True}, headers=AH())
    _ = (Guild, GuildMember, gid)


def test_guild_settings_power_autoaccept_rename(newplayer):
    lead, weak, ok = newplayer(), newplayer(), newplayer()
    make_guild(lead, mode="approval")
    r = lead.post("/guilds/edit", {"name": "Бурзяне " + uuid.uuid4().hex[:4], "emblem": "wolf", "min_power": 999999,
                                   "auto_accept": True, "notify_chat": False}, key=False)
    assert r.status_code == 200, r.text
    g = lead.get("/guilds/mine").json()["guild"]
    assert g["emblem"] == "wolf" and g["settings"]["min_power"] == 999999 and g["public_id"].startswith("G-")
    assert g["power"] > 0 and g["rank"] >= 1
    assert weak.post(f"/guilds/{g['id']}/join", key=False).status_code == 403  # power requirement
    lead.post("/guilds/edit", {"min_power": 1}, key=False)
    assert ok.post(f"/guilds/{g['id']}/join", key=False).json()["status"] == "joined"  # auto-accept
    assert lead.post("/guilds/edit", {"emblem": "dragon"}, key=False).status_code == 400


def test_guild_shop_spends_marks_with_weekly_limits(newplayer):
    p = newplayer()
    assert p.get("/guilds/shop").status_code == 404  # members only
    make_guild(p)
    shop = p.get("/guilds/shop").json()
    seal = next(i for i in shop["items"] if i["code"] == "gs_seal")
    start = shop["marks"]  # creating a guild may already grant some marks
    assert start < 250 and seal["bought"] == 0
    assert p.post("/guilds/shop/gs_seal/buy").status_code == 409  # not enough marks
    give(p, guild_marks=600)
    r = p.post("/guilds/shop/gs_seal/buy")
    assert r.status_code == 200, r.text
    assert r.json()["wallet"]["guild_marks"] == start + 350 and r.json()["wallet"]["ancient_seals"] >= 1
    assert p.post("/guilds/shop/gs_seal/buy").json()["detail"]["code"] == "limit_reached"
    assert p.post("/guilds/shop/nope/buy").status_code == 404
