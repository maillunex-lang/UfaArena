"""Living World AI phase 4: relationships and groups (stage 6), chat channels (stage 8, D-11), guild alliances (D-12)
and guild AI (stage 9), interaction with real players with privacy and limits (stage 16)."""
import random
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.test_social import AH, ADMIN, friends, give, make_guild, public_id, session, set_profile, uid  # noqa: F401


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def _ai(db, n, seed):
    from app.social.ai.population import create_persona
    rng = random.Random(seed)
    out = [create_persona(db, rng) for _ in range(n)]
    db.flush()
    return out


def test_relationships_labels_reputation_and_groups(client):
    from app.ai import social as SOC
    from app.models import AiSocialGroupMember
    with session() as db:
        ps = _ai(db, 5, 401)
        a, b, c = ps[0].user_id, ps[1].user_id, ps[2].user_id
        for _ in range(4):
            SOC.mutual(db, a, b, "friend")
        assert SOC.label(SOC.get(db, a, b, create=False)) in ("близкие друзья", "приятели")
        for _ in range(8):
            SOC.relate(db, a, c, "arena_loss")
        assert SOC.get(db, a, c, create=False).rivalry > 0.5 and "соперник" in SOC.label(SOC.get(db, a, c, create=False))
        assert SOC.reputation(db, b) > 0
        # personas that like each other form an informal group
        for x in ps[1:4]:
            for y in ps[1:4]:
                if x is not y:
                    for _ in range(3):
                        SOC.relate(db, x.user_id, y.user_id, "friend")
        assert SOC.form_groups(db, random.Random(1), max_new=1) == 1
        g = SOC.group_of(db, ps[1].user_id)
        assert g is not None and len(SOC.members(db, g.id)) >= 3
        assert db.query(AiSocialGroupMember).filter(AiSocialGroupMember.group_id == g.id).count() >= 3


def test_channels_access_news_read_only_and_switches(client, newplayer):
    p = newplayer()
    chans = {c["channel"]: c for c in p.get("/chat/channels").json()["channels"]}
    assert "news" in chans and chans["news"]["read_only"] is True
    region = next(c for c in chans if c.startswith("region:"))
    assert p.post("/chat/send", {"channel": region, "text": "Привет, земляки!"}, key=False).status_code == 200
    assert p.get(f"/chat/messages?channel={region}").status_code == 200
    assert p.post("/chat/send", {"channel": "news", "text": "Можно?"}, key=False).status_code == 403
    assert p.get("/chat/messages?channel=region:r9_nowhere").status_code == 403  # not my region
    # admin posts an announcement
    assert client.post("/admin/api/web/chat", headers=AH(), json={"channel": "news", "text": "Технические работы в 3:00"}).status_code == 200
    msgs = p.get("/chat/messages?channel=news").json()["messages"]
    assert any("Технические работы" in m["text"] for m in msgs)
    # switched off in the admin panel -> gone
    assert client.post("/admin/api/ai/settings/channels", headers=AH(), json={"region_enabled": False}).status_code == 200
    chans = [c["channel"] for c in p.get("/chat/channels").json()["channels"]]
    assert not any(c.startswith("region:") for c in chans)
    assert p.get(f"/chat/messages?channel={region}").status_code == 403
    client.post("/admin/api/ai/settings/channels", headers=AH(), json={"region_enabled": True})


def test_guild_alliances_chat_and_no_war_between_allies(client, newplayer):
    a, b, c, d = newplayer(), newplayer(), newplayer(), newplayer()
    ga, gb, gc, gd = make_guild(a), make_guild(b), make_guild(c), make_guild(d)
    assert a.post("/alliances/propose", {"guild_id": ga}).status_code == 400  # own guild
    r = a.post("/alliances/propose", {"guild_id": gb}).json()
    assert r["status"] == "pending"
    inc = b.get("/alliances/mine").json()["incoming"]
    assert inc and inc[0]["guild"]["id"] == ga
    r = b.post(f"/alliances/proposals/{inc[0]['id']}/accept").json()
    assert r["alliance"] and len(r["alliance"]["guilds"]) == 2
    ch = r["alliance"]["channel"]
    assert a.post("/chat/send", {"channel": ch, "text": "Союзники, привет!"}, key=False).status_code == 200
    assert b.get(f"/chat/messages?channel={ch}").status_code == 200
    assert c.get(f"/chat/messages?channel={ch}").status_code == 403
    # third guild joins, fourth cannot (max 3)
    a.post("/alliances/propose", {"guild_id": gc})
    p3 = c.get("/alliances/mine").json()["incoming"][0]["id"]
    assert len(c.post(f"/alliances/proposals/{p3}/accept").json()["alliance"]["guilds"]) == 3
    assert a.post("/alliances/propose", {"guild_id": gd}).status_code == 409
    # allies are never matched against each other in guild wars
    from app.social.alliances import allies
    with session() as db:
        assert set(allies(db, ga)) == {gb, gc}
    # leaving: an alliance of one dissolves
    assert c.post("/alliances/leave").status_code == 200
    assert b.post("/alliances/leave").status_code == 200
    assert a.get("/alliances/mine").json()["alliance"] is None


def test_guild_ai_founding_roles_elections_only_in_ai_guilds(client):
    from app.ai import guild_ai as GAI
    from app.models import Guild, GuildMember
    with session() as db:
        _ai(db, 14, 501)
        s = {**GAI.SECTION.get(db), "max_ai_guilds": 50, "found_min_free": 6}
        g = GAI.found_guild(db, random.Random(3), s)
        assert g is not None and g.is_ai
        n = db.query(GuildMember).filter(GuildMember.guild_id == g.id).count()
        assert n >= 5
        assert GAI.assign_roles(db, g) >= 0
        st = GAI.state(db, g)
        assert st.traditions and st.history[0]["kind"] == "founded"
        st.next_election_at = __import__("app.core.db", fromlist=["utcnow"]).utcnow() - timedelta(minutes=1)
        res = GAI.run_election(db, g, random.Random(4), s)
        assert res is not None and res["winner"] in {m.user_id for m in db.query(GuildMember).filter(GuildMember.guild_id == g.id)}
        assert db.get(Guild, g.id).leader_id == res["winner"]
        gid = g.id
    # the admin endpoint refuses elections in players' guilds
    with session() as db:
        real = db.scalar(select(Guild).where(Guild.is_ai.is_(False)))
    if real is not None:
        assert client.post(f"/admin/api/ai/guilds/{real.id}/election", headers=AH()).status_code == 400
    assert client.post(f"/admin/api/ai/guilds/{gid}/election", headers=AH()).status_code == 200
    d = client.get("/admin/api/ai/guilds", headers=AH()).json()
    assert any(x["id"] == gid and x["is_ai"] for x in d["items"])


def test_ai_guild_answers_alliance_and_welcomes_newcomer(client, newplayer):
    from app.ai import guild_ai as GAI
    from app.models import Guild
    from app.social.ai import banter
    with session() as db:
        _ai(db, 10, 601)
        g = GAI.found_guild(db, random.Random(5), {**GAI.SECTION.get(db), "max_ai_guilds": 50, "found_min_free": 6})
        gid = g.id
        g.join_mode = "open"
    lead = newplayer()
    mine = make_guild(lead)
    r = lead.post("/alliances/propose", {"guild_id": gid}).json()
    assert r["status"] in ("accepted", "declined")  # an AI guild answers right away
    # a real newcomer joining an AI guild is greeted in the guild chat (paced queue)
    banter._queue.clear()
    p = newplayer()
    set_profile(p, level=5)
    assert p.post(f"/guilds/{gid}/join").status_code == 200
    assert any(it[2] == f"guild:{gid}" for it in banter._queue)
    banter._queue.clear()
    with session() as db:
        assert db.get(Guild, mine) is not None


def test_outreach_privacy_limits_exceptions_and_triggers(client, newplayer):
    from app.ai import outreach as OUT
    from app.core.db import utcnow
    from app.models import AiPlayerWatch, ChatMessage, PlayerProfile, UserBlock
    with session() as db:
        _ai(db, 6, 701)
    p = newplayer()  # a brand new player who is online now
    set_profile(p, last_seen_at=utcnow(), age_group="adult")
    s_on = {"initiative": 100}
    client.post("/admin/api/ai/settings/outreach", headers=AH(), json=s_on)

    def dms():
        with session() as db:
            return db.query(ChatMessage).filter(ChatMessage.channel.like(f"dm:%{uid(p)}%"), ChatMessage.is_ai.is_(True)).count()

    # opted out -> nothing
    assert p.post("/social/ai-prefs", {"ai_contact": False}, key=False).json()["prefs"]["ai_contact"] is False
    with session() as db:
        assert OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(1), OUT.SECTION.get(db)) is None
    assert dms() == 0
    p.post("/social/ai-prefs", {"ai_contact": True}, key=False)
    # admin exception -> nothing
    assert client.post("/admin/api/ai/outreach/exceptions", headers=AH(), json={"uralia_id": public_id(p), "add": True}).status_code == 200
    with session() as db:
        assert OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(1), OUT.SECTION.get(db)) is None
    client.post("/admin/api/ai/outreach/exceptions", headers=AH(), json={"uralia_id": public_id(p), "add": False})
    # welcome for a new player, from an AI, marked as AI
    with session() as db:
        t = OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(2), OUT.SECTION.get(db))
    assert t == "welcome_new" and dms() == 1
    # never several in a row (20 min) and never above the daily limit
    with session() as db:
        assert OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(3), OUT.SECTION.get(db)) is None
        w = db.get(AiPlayerWatch, uid(p))
        w.contacted_at = utcnow() - timedelta(hours=1)
        w.contacts_today = 2
    with session() as db:
        assert OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(4), OUT.SECTION.get(db)) is None
    # congratulations when crossing a level milestone
    with session() as db:
        w = db.get(AiPlayerWatch, uid(p))
        w.contacts_today, w.level = 0, 4
        db.get(PlayerProfile, uid(p)).level = 5
    with session() as db:
        t = OUT.consider(db, db.get(PlayerProfile, uid(p)), random.Random(5), OUT.SECTION.get(db))
    assert t == "congratulate"
    # a blocked AI never writes
    with session() as db:
        msg = db.query(ChatMessage).filter(ChatMessage.channel.like(f"dm:%{uid(p)}%"), ChatMessage.is_ai.is_(True)).first()
        db.add(UserBlock(user_id=uid(p), blocked_id=msg.user_id))
    with session() as db:
        from app.models import AiPersona
        persona = db.scalar(select(AiPersona).where(AiPersona.user_id == msg.user_id))
        assert OUT.may_contact(db, db.get(PlayerProfile, uid(p)), persona)[0] is False
    # admin history of communication
    h = client.get(f"/admin/api/ai/players/{public_id(p)}", headers=AH()).json()
    assert len(h["messages"]) >= 2 and all(m["from_ai"] for m in h["messages"])


def test_director_social_life_runs_without_errors(client):
    from app.ai import settings as ST
    from app.ai.director import Director
    from app.core.db import utcnow
    from app.models import PlayerProfile
    with session() as db:
        _ai(db, 8, 801)
        real = db.scalar(select(PlayerProfile).where(PlayerProfile.is_ai.is_(False)))
        if real is not None:
            real.last_seen_at = utcnow()
        ST.update(db, {"mode": "normal", "social_life": 1}, "test")
    with session() as db:
        d = Director()
        out = d.tick(db)
        for k in ("outreach", "guilds", "groups"):
            assert k in out and "error" not in (out[k] or {}), out.get(k)
        ST.update(db, {"mode": "test"}, "test")


def test_age_gate_minors_never_get_ai_dms_adults_get_flirt(client, newplayer):
    """Decision D-C1: hero setup with an 18+ answer; minors / unknown age never get AI private messages or adult
    content; adults get flirt (the 18+ toggle on by default) and a stop phrase ends it."""
    import random as _r
    from app.ai import adult as ADULT
    from app.ai import outreach as OUT
    from app.core.db import utcnow
    from app.models import AiEvent, AiPersona, AiPlayerWatch, ChatMessage, PlayerProfile
    from app.social import chat as CH
    from app.social.ai.control import adult_ok
    with session() as db:
        ps = _ai(db, 6, 901)
        for p_ in ps:
            p_.style = "flirty"
        ai_uid = ps[0].user_id
    kid, adult = newplayer(), newplayer()
    me = kid.get("/player/me").json()["profile"]
    assert me["needs_setup"] is True and me["age_group"] is None
    # unknown age = minor: no AI DMs, no replies
    CH._recent.clear()
    kid.post("/chat/send", {"to_user": ai_uid, "text": "привет, красотка 😘"}, key=False)
    with session() as db:
        assert not [e for e in db.query(AiEvent).filter(AiEvent.kind == "dm") if (e.payload or {}).get("to_user") == uid(kid)]
        assert OUT.may_contact(db, db.get(PlayerProfile, uid(kid)))[0] is False
    r = kid.post("/player/setup", {"nickname": "Малыш_Тест", "adult": False}).json()["profile"]
    assert r["age_group"] == "minor" and r["needs_setup"] is False and r["nickname"] == "Малыш_Тест"
    prefs = kid.get("/social/ai-prefs").json()
    assert "adult_content" not in prefs["names"]
    kid.post("/social/ai-prefs", {"adult_content": True}, key=False)  # a minor cannot turn it on
    with session() as db:
        assert adult_ok(db.get(PlayerProfile, uid(kid))) is False
        set_profile(kid, last_seen_at=utcnow())
    with session() as db:
        assert OUT.consider(db, db.get(PlayerProfile, uid(kid)), _r.Random(1), {**OUT.SECTION.get(db), "initiative": 100}) is None
    # adult: 18+ toggle on by default, flirt outreach and flirty replies
    assert adult.post("/player/setup", {"adult": True}).json()["profile"]["age_group"] == "adult"
    assert adult.get("/social/ai-prefs").json()["prefs"]["adult_content"] is True
    set_profile(adult, last_seen_at=utcnow(), created_at=utcnow() - timedelta(days=30))
    with session() as db:
        w = OUT.watch(db, uid(adult))
        w.flags = {"greeted": True, "helped": True, "met": True}
    got = None
    for seed in range(40):
        with session() as db:
            w = db.get(AiPlayerWatch, uid(adult))
            w.contacted_at, w.contacts_today = None, 0
            got = OUT.consider(db, db.get(PlayerProfile, uid(adult)), _r.Random(seed),
                               {**OUT.SECTION.get(db), "initiative": 100, "first_contact": False, "invite_guild": False,
                                "invite_events": False, "offer_help": False})
        if got == "flirt":
            break
    assert got == "flirt"
    with session() as db:
        msgs = [m.text for m in db.query(ChatMessage).filter(ChatMessage.channel.like(f"dm:%{uid(adult)}%"), ChatMessage.is_ai.is_(True))]
        assert msgs and all(ADULT.safe(t) for t in msgs)
        from app.social.ai.population import handle_dm
        p0 = db.query(AiPersona).filter(AiPersona.user_id == ai_uid).one()
        assert handle_dm(db, ai_uid, uid(adult), None, "ты такая милашка 😘") is True
        assert handle_dm(db, ai_uid, uid(kid), None, "ты такая милашка 😘") is False  # never to a minor
        assert p0 is not None
    # a stop phrase ends flirting
    CH._recent.clear()
    adult.post("/chat/send", {"to_user": ai_uid, "text": "не пиши мне больше такое, отстань"}, key=False)
    with session() as db:
        assert db.get(AiPlayerWatch, uid(adult)).flags.get("no_flirt") is True
        assert OUT._flirt_ok(db, db.get(PlayerProfile, uid(adult)), db.get(AiPlayerWatch, uid(adult)),
                             db.get(AiPlayerWatch, uid(adult)).flags, OUT.SECTION.get(db)) is False
    # adult switched 18+ off -> no flirt
    adult.post("/social/ai-prefs", {"adult_content": False}, key=False)
    with session() as db:
        assert adult_ok(db.get(PlayerProfile, uid(adult))) is False
