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


def test_campaign_editor_regions_nodes_order_hide_and_progress(client, newplayer):
    from app.game.seed import seed_static
    from app.models import CampaignNode, PlayerCampaignProgress
    from app.services import ordered_nodes
    rc = "r_t" + uuid.uuid4().hex[:6]
    assert client.post("/admin/api/game/campaign/regions", headers=AH(),
                       json={"code": rc, "fields": {"name": "Тестовая земля", "order": 90, "description": "Глава для теста"}}).status_code == 200
    en = [{"hero_code": "e_minion", "level": 3, "slot": 0}, {"hero_code": "e_minion", "level": 3, "slot": 1}]
    codes = []
    for i in range(3):
        c = f"{rc}-{i + 1}"
        r = client.post("/admin/api/game/campaign/nodes", headers=AH(), json={"code": c, "fields": {
            "region_code": rc, "order": i + 1, "name": f"Этап {i + 1}", "territory": "nature", "enemies": en,
            "rewards": {"gold": 100}, "story": [{"speaker": "narrator", "text": "Тест."}]}})
        assert r.status_code == 200, r.text
        codes.append(c)
    bad = {"region_code": rc, "order": 9, "name": "x", "territory": "nature", "enemies": [{"hero_code": "nope", "level": 1, "slot": 0}]}
    assert client.post("/admin/api/game/campaign/nodes", headers=AH(), json={"code": rc + "-x", "fields": bad}).status_code == 400
    p = newplayer()
    reg = next(r for r in p.get("/campaign").json()["regions"] if r["code"] == rc)
    assert [n["code"] for n in reg["nodes"]] == codes and reg["nodes"][0]["story"]
    # reorder, hide; a player's cleared stage stays cleared
    assert client.post("/admin/api/game/campaign/nodes/reorder", headers=AH(), json={"region_code": rc, "codes": [codes[2], codes[0], codes[1]]}).status_code == 200
    reg = next(r for r in p.get("/campaign").json()["regions"] if r["code"] == rc)
    assert [n["code"] for n in reg["nodes"]] == [codes[2], codes[0], codes[1]]
    with session() as db:
        db.add(PlayerCampaignProgress(user_id=uid(p), node_code=codes[0], best_turns=5))
    assert client.post(f"/admin/api/game/campaign/nodes/{codes[0]}/hide", headers=AH(), json={"hidden": True}).status_code == 200
    with session() as db:
        assert codes[0] not in [n.code for n in ordered_nodes(db)]
        assert db.get(PlayerCampaignProgress, (uid(p), codes[0])) is not None  # progress kept
    assert client.delete(f"/admin/api/game/campaign/nodes/{codes[0]}/override", headers=AH()).status_code == 409  # cleared: hide only
    # difficulty check with the real engine
    sim = client.get(f"/admin/api/game/campaign/nodes/{codes[1]}/simulate?level=20", headers=AH()).json()
    assert sim["win_pct"] >= 0 and len(sim["team"]) == 5
    # map editor: stage checkpoints and world map position; both survive a re-seed
    assert client.put("/admin/api/game/campaign/map/nodes", headers=AH(), json={"positions": {codes[1]: [3, 1]}}).status_code == 200
    assert client.put("/admin/api/game/campaign/map/world", headers=AH(), json={"positions": {rc: [0.2, 0.3]}}).status_code == 200
    assert client.put("/admin/api/game/campaign/map/world", headers=AH(), json={"positions": {rc: [2, 0.3]}}).status_code == 400
    with session() as db:
        seed_static(db)
    reg = next(r for r in p.get("/campaign").json()["regions"] if r["code"] == rc)
    assert reg["map_xy"] == [0.2, 0.3] and next(n for n in reg["nodes"] if n["code"] == codes[1])["map_pos"] == [3, 1]
    m = client.get("/admin/api/game/campaign/map", headers=AH()).json()
    assert any(r["code"] == rc and r["world"] == [0.2, 0.3] for r in m["regions"]) and m["roads"]
    # hiding the whole chapter removes it from the player's campaign
    assert client.post(f"/admin/api/game/campaign/regions/{rc}/hide", headers=AH(), json={"hidden": True}).status_code == 200
    assert not any(r["code"] == rc for r in p.get("/campaign").json()["regions"])
    with session() as db:
        assert db.get(CampaignNode, codes[1]) is not None
