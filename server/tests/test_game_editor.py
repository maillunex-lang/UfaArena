"""Admin game editor: heroes created/edited/disabled through an override layer that survives re-seeding; balance report."""
import uuid

import pytest

from tests.test_social import AH, ADMIN, session, uid  # noqa: F401


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


def _new_code():
    return "test_" + uuid.uuid4().hex[:8]


BASE = {"name": "Тестовый батыр", "faction_code": "stone_sky", "class_code": "warrior", "rarity": 3, "base_hp": 1200,
        "base_atk": 90, "base_def": 55, "base_spd": 100}


def test_create_edit_survives_reseed_and_catalog(client, newplayer):
    from app.game.seed import seed_static
    from app.models import Hero
    code = _new_code()
    assert client.post("/admin/api/game/heroes", json={"code": code, "fields": BASE}).status_code in (401, 403)
    r = client.post("/admin/api/game/heroes", headers=AH(), json={"code": code, "fields": BASE})
    assert r.status_code == 200 and r.json()["custom"] is True
    assert client.post("/admin/api/game/heroes", headers=AH(), json={"code": code, "fields": BASE}).status_code == 409
    assert client.post("/admin/api/game/heroes", headers=AH(), json={"code": "Bad Code", "fields": BASE}).status_code == 400
    assert client.post("/admin/api/game/heroes", headers=AH(), json={"code": _new_code(), "fields": {**BASE, "rarity": 9}}).status_code == 400
    p = newplayer()
    assert any(h["code"] == code for h in p.get("/heroes").json()["heroes"])
    # edit an existing code hero and the new one; a re-seed (restart / update) keeps both edits
    assert client.put("/admin/api/game/heroes/ilgiz", headers=AH(), json={"fields": {"base_atk": 70}}).status_code == 200
    assert client.put(f"/admin/api/game/heroes/{code}", headers=AH(), json={"fields": {"base_hp": 1500}}).status_code == 200
    with session() as db:
        seed_static(db)
    with session() as db:
        assert db.get(Hero, "ilgiz").base_atk == 70 and db.get(Hero, code).base_hp == 1500
    # reset the code hero back to the game version
    assert client.delete("/admin/api/game/heroes/ilgiz/override", headers=AH()).status_code == 200
    from app.game import data as D
    with session() as db:
        assert db.get(Hero, "ilgiz").base_atk == next(h for h in D.HEROES if h["code"] == "ilgiz")["base_atk"]


def test_disable_keeps_owned_and_rollback(client, newplayer):
    from app.models import Hero, PlayerHero
    code = _new_code()
    client.post("/admin/api/game/heroes", headers=AH(), json={"code": code, "fields": BASE})
    owner, other = newplayer(), newplayer()
    with session() as db:
        db.add(PlayerHero(user_id=uid(owner), hero_code=code))
    assert client.post(f"/admin/api/game/heroes/{code}/disable", headers=AH(), json={"disabled": True}).json()["disabled"]
    with session() as db:
        assert db.get(Hero, code).summonable is False
    assert not any(h["code"] == code for h in other.get("/heroes").json()["heroes"])
    assert any(h["code"] == code for h in owner.get("/heroes").json()["heroes"])  # the owner keeps it
    assert client.delete(f"/admin/api/game/heroes/{code}/override", headers=AH()).status_code == 409  # owned: disable only
    # rollback undoes the last change (the disable)
    r = client.post("/admin/api/game/rollback", headers=AH()).json()
    assert r["undid"] == "hero_disable"
    assert any(h["code"] == code for h in other.get("/heroes").json()["heroes"])
    assert client.get("/admin/api/game/history", headers=AH()).json()["items"]


def test_kit_validation_and_balance_flags_one_shot(client):
    code = _new_code()
    bad_kit = {"basic": {"name": "x", "effects": [{"type": "damage", "target": "target", "mult": 9, "hits": 3}]}}
    assert client.post("/admin/api/game/heroes", headers=AH(), json={"code": code, "fields": {**BASE, "kit": bad_kit}}).status_code == 400
    kit = {"basic": {"name": "Удар", "effects": [{"type": "damage", "target": "target", "mult": 1.0}]}, "skills": [],
           "ultimate": {"name": "Испепеление", "effects": [{"type": "damage", "target": "target", "mult": 14.0}]}, "passive": None, "mechanic": None}
    f = {**BASE, "name": "Имба", "base_atk": 2500, "kit": kit, "extra": {"crit": 0.5, "crit_dmg": 3.0}}
    assert client.post("/admin/api/game/heroes", headers=AH(), json={"code": code, "fields": f}).status_code == 200
    r = client.get("/admin/api/game/balance?level=40&duels=1", headers=AH()).json()
    imba = next(h for h in r["heroes"] if h["code"] == code)
    assert imba["max_skill"] == "Испепеление" and any("одного удара" in x for x in imba["flags"])
    assert code in r["flagged"] and imba["duel_win_pct"] >= 50
    client.post(f"/admin/api/game/heroes/{code}/disable", headers=AH(), json={"disabled": True})
    r = client.get("/admin/api/game/balance?level=40", headers=AH()).json()
    assert code not in [h["code"] for h in r["heroes"]]  # disabled heroes leave the report
    m = client.get("/admin/api/game/meta", headers=AH()).json()
    assert m["factions"] and m["classes"] and "knight" in m["rigs"]
