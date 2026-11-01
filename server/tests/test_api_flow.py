"""End-to-end MVP loop: guest -> onboarding -> battle -> rewards -> summon -> AFK -> fortress -> quests -> mail,
and 'restart' (new token via refresh) shows the same server progress."""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import PlayerProfile
from app.services import ledger_consistent


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_full_mvp_loop(client, newplayer):
    p = newplayer()
    boot = p.get("/player/bootstrap").json()
    assert len(boot["heroes"]) == 4
    assert {h["hero_code"] for h in boot["heroes"]} == {"azamat", "yurek", "safariy", "tan_chechek"}
    assert all("kit" in h and h["kit"]["ultimate"] for h in boot["heroes"])
    assert boot["campaign"]["next_node"] == "1-1"
    gold0 = boot["wallet"]["gold"]

    # battle 1-1 with the starter formation
    for _ in range(5):
        b = p.post("/battles/validate", {"node_id": "1-1"}, key=False).json()
        if b["simulation"]["result"] == "victory":
            break
    assert b["simulation"]["result"] == "victory"
    key = "complete-1-1-abcdef"
    done = p.post("/campaign/1-1/complete", {"battle_id": b["battle_id"]}, key=key).json()
    assert done["first_clear"] and done["rewards"]["gold"] == 120 and done["next_node"] == "1-2"
    assert done["exp_gained"] > 0 and done["level"] >= 1 and done["campaign_progress"]["cleared"] == 1
    # retry with the same key replays, no double reward
    again = p.post("/campaign/1-1/complete", {"battle_id": b["battle_id"]}, key=key).json()
    assert again["replayed"] and again["wallet"] == done["wallet"]
    # a new key for the same battle is rejected
    r = p.post("/campaign/1-1/complete", {"battle_id": b["battle_id"]})
    assert r.status_code == 409

    # mail
    mail = p.get("/mail").json()["mail"]
    assert mail and not mail[0]["claimed"]
    m = p.post(f"/mail/{mail[0]['id']}/claim").json()
    assert m["rewards"]["summon_essence"] == 5
    assert p.post(f"/mail/{mail[0]['id']}/claim").status_code == 409

    # summon: first pull is the onboarding guarantee
    s = p.post("/summon", {"pool": "standard", "count": 1}).json()
    assert s["results"][0]["hero_code"] == "ai_tulgan"
    s10 = p.post("/summon", {"pool": "standard", "count": 1}).json()
    assert len(s10["results"]) == 1

    # quests: first quest claimable
    qs = {q["code"]: q for q in p.get("/quests").json()["quests"]}
    assert qs["main_first_battle"]["claimable"]
    qc = p.post("/quests/main_first_battle/claim").json()
    assert qc["rewards"] == {"gold": 300, "crystals": 100}
    assert p.post("/quests/main_first_battle/claim").status_code == 409

    # AFK uses server time: move last claim 2h into the past
    with Session(get_engine()) as db:
        prof = db.get(PlayerProfile, p.tokens["user_id"])
        prof.afk_last_claim_at = prof.afk_last_claim_at - timedelta(hours=2)
        db.commit()
    afk = p.post("/rewards/afk/claim").json()
    assert afk["credited_s"] >= 7200 - 5 and afk["rewards"]["gold"] > 0
    assert p.post("/rewards/afk/claim").status_code == 409  # too soon

    # fortress + level up
    f = p.post("/fortress/buildings/forge/upgrade").json()
    assert next(b for b in f["buildings"] if b["code"] == "forge")["level"] == 2
    hero_id = boot["heroes"][0]["id"]
    lv = p.post(f"/player/heroes/{hero_id}/level-up").json()
    assert lv["hero"]["level"] == 2

    # "restart": refresh token -> new session sees identical server progress
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": p.tokens["refresh_token"]})
    assert r.status_code == 200
    old_refresh = p.tokens["refresh_token"]
    p.tokens = r.json()
    boot2 = p.get("/player/bootstrap").json()
    assert "1-1" in boot2["campaign"]["cleared"] and len(boot2["heroes"]) >= 4
    assert boot2["wallet"]["gold"] > gold0
    # refresh-token reuse revokes the family
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
    assert p.get("/player/me").status_code == 401

    with Session(get_engine()) as db:
        assert ledger_consistent(db, p.tokens["user_id"])


def test_campaign_lock_and_ownership(newplayer):
    a, b = newplayer(), newplayer()
    assert a.post("/battles/validate", {"node_id": "1-3"}, key=False).status_code == 403
    other = b.get("/player/heroes").json()["heroes"][0]["id"]
    r = a.post("/formation", {"slots": [other, None, None, None, None]}, key=False)
    assert r.status_code == 403
    r = a.post(f"/player/heroes/{other}/level-up")
    assert r.status_code == 404


def test_insufficient_funds_and_idempotency_conflict(newplayer):
    p = newplayer()
    r = p.post("/summon", {"pool": "standard", "count": 10})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "insufficient_funds"
    k = "same-key-123456"
    assert p.post("/summon", {"pool": "standard", "count": 1}, key=k).status_code == 200
    r = p.post("/summon", {"pool": "standard", "count": 10}, key=k)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "idempotency_conflict"


def test_auth_required_and_bad_token(client):
    assert client.get("/api/v1/player/me").status_code == 401
    assert client.get("/api/v1/player/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40}).status_code == 401


def test_link_and_login(client, newplayer):
    import uuid
    p = newplayer()
    email = f"hero-{uuid.uuid4().hex[:8]}@example.com"
    r = p.post("/auth/link", {"email": email, "password": "secret-pass-1"}, key=False)
    assert r.status_code == 200
    bad = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass-1"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/login", json={"email": email, "password": "secret-pass-1"})
    assert ok.status_code == 200 and ok.json()["user_id"] == p.tokens["user_id"]
    # the profile tells the client this is a linked account (email is masked)
    prof = client.get("/api/v1/player/me", headers={"Authorization": "Bearer " + ok.json()["access_token"]}).json()["profile"]
    assert prof["account_kind"] == "linked" and prof["email_masked"].startswith(email[:2] + "***@")
    assert email not in str(prof)


def test_password_change_and_recovery(client, newplayer):
    import uuid
    p = newplayer()
    email = f"rec-{uuid.uuid4().hex[:8]}@example.com"
    r = p.post("/auth/link", {"email": email, "password": "secret-pass-1"}, key=False)
    code = r.json()["recovery_code"]
    assert len(code) == 14 and code.count("-") == 2
    # wrong old password is rejected; right one changes it
    assert p.post("/auth/password", {"old_password": "nope-nope", "new_password": "secret-pass-2"}, key=False).status_code == 401
    assert p.post("/auth/password", {"old_password": "secret-pass-1", "new_password": "secret-pass-2"}, key=False).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "secret-pass-2"}).status_code == 200
    # recovery: bad code rejected, good code sets a new password and rotates the code
    bad = client.post("/api/v1/auth/recover", json={"email": email, "code": "AAAA-BBBB-CCCC", "new_password": "secret-pass-3"})
    assert bad.status_code == 401
    ok = client.post("/api/v1/auth/recover", json={"email": email, "code": code.lower(), "new_password": "secret-pass-3"})
    assert ok.status_code == 200 and ok.json()["user_id"] == p.tokens["user_id"] and ok.json()["recovery_code"] != code
    again = client.post("/api/v1/auth/recover", json={"email": email, "code": code, "new_password": "secret-pass-4"})
    assert again.status_code == 401  # one-time
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "secret-pass-3"}).status_code == 200
    # old sessions were signed out
    assert p.get("/player/me").status_code == 401


def test_signed_manifest(client):
    from app.core import signing
    d = client.get("/api/v1/content/manifest?channel=dev&client_version=0.1.0").json()
    assert signing.verify(d["manifest"], d["signature"])
    assert d["manifest_raw"].encode() == signing.canonical(d["manifest"])
    tampered = dict(d["manifest"], version=999)
    assert not signing.verify(tampered, d["signature"])
    pkg = d["manifest"]["packages"][0]
    import hashlib
    raw = client.get(pkg["url"]).content
    assert hashlib.sha256(raw).hexdigest() == pkg["sha256"] and len(raw) == pkg["size"]


def test_rate_limit(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "auth_rate_limit_per_minute", 3)
    codes = [client.post("/api/v1/auth/guest", json={"device_id": "rl-device-0001"}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]


def test_campaign_chapters(newplayer):
    p = newplayer()
    regions = p.get("/campaign").json()["regions"]
    assert len(regions) == 7 and sum(len(r["nodes"]) for r in regions) == 68
    assert [r["order"] for r in regions] == sorted(r["order"] for r in regions)
    assert all(len(r["nodes"]) == 10 for r in regions[1:]) and regions[-1]["nodes"][-1]["is_boss"]
    assert regions[0]["nodes"][0]["unlocked"] and not regions[1]["nodes"][0]["unlocked"]
    # chapter 2 opens exactly when the last stage of chapter 1 is cleared
    from app.core.db import get_db
    from app.models import PlayerCampaignProgress
    gen = get_db()
    db = next(gen)
    try:
        for n in regions[0]["nodes"]:
            db.add(PlayerCampaignProgress(user_id=p.tokens["user_id"], node_code=n["code"], best_turns=1))
        db.commit()
    finally:
        gen.close()
    regions = p.get("/campaign").json()["regions"]
    assert regions[1]["nodes"][0]["unlocked"] and not regions[1]["nodes"][1]["unlocked"]
    assert p.get("/player/bootstrap").json()["campaign"]["next_node"] == "2-1"


def test_player_summary(newplayer):
    p = newplayer()
    s = p.get("/player/summary").json()
    assert s["campaign"]["total"] >= 60 and s["campaign"]["next"]["code"] == "1-1"
    assert s["mail_unclaimed"] >= 1 and "afk" in s and "social" in s and s["quests"]["daily_total"] >= 1
