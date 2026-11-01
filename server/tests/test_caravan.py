"""Lore stage S4: caravan modules keep fortress levels, council influence is hidden and derived, travel follows roads."""
from datetime import timedelta


def _db():
    from app.core.db import get_db
    gen = get_db()
    return gen, next(gen)


def clear_until(p, last_code):
    from app.game import data as D
    from app.models import PlayerCampaignProgress
    gen, db = _db()
    try:
        for n in D.NODES:
            if db.get(PlayerCampaignProgress, (p.tokens["user_id"], n["code"])) is None:
                db.add(PlayerCampaignProgress(user_id=p.tokens["user_id"], node_code=n["code"], best_turns=1))
            if n["code"] == last_code:
                break
        db.commit()
    finally:
        gen.close()


def test_caravan_modules_council_and_hidden_influence(newplayer):
    p = newplayer()
    c = p.get("/caravan").json()
    codes = {m["code"] for m in c["modules"]}
    assert {"summon_hall", "forge", "training", "alchemy", "storage", "guild_house", "library", "research", "towers"} == codes
    names = {m["code"]: m["name"] for m in c["modules"]}
    assert names["storage"] == "Торговые повозки" and names["alchemy"] == "Лазарет"
    assert c["location"] == "r1_shikhany" and c["location_bonus"] and not c["traveling"]
    council = {m["code"]: m for m in c["council"]}
    assert set(council) == {"azamat", "gauhar", "ilsur", "gulnaz", "yurek", "zarkhan"}
    assert all("influence" not in m for m in c["council"])  # hidden (C17)
    assert c["leader"] is None  # nobody has influence yet
    # upgrading towers (Azamat oversees them) makes Azamat the leader -> +2% hp on top of modules
    from app.services import grant
    gen, db = _db()
    try:
        grant(db, p.tokens["user_id"], {"gold": 100000, "nature_essence": 1000}, "test")
        db.commit()
    finally:
        gen.close()
    before = p.get("/player/heroes").json()["heroes"][0]["stats"]
    r = p.post("/fortress/buildings/towers/upgrade")
    assert r.status_code == 200
    c = p.get("/caravan").json()
    assert c["leader"] == "azamat" and {m["code"]: m["mood"] for m in c["council"]}["azamat"] == "lead"
    after = p.get("/player/heroes").json()["heroes"][0]["stats"]
    assert after["def"] > before["def"] and after["hp"] > before["hp"]


def test_caravan_travel_roads_and_arrival(newplayer):
    p = newplayer()
    c = p.get("/caravan").json()
    roads = {r["to"]: r for r in c["roads"]}
    assert set(roads) == {"r4_nugush", "r6_ufa_plateau", "r3_shulgantash"}
    assert not roads["r4_nugush"]["open"]  # land IV is not reached in the campaign yet
    assert p.post("/caravan/travel", {"to": "r4_nugush"}).status_code == 403
    assert p.post("/caravan/travel", {"to": "r7_zilair"}).status_code == 400  # no direct road
    clear_until(p, "1-8")  # chapter 1 done -> land II opens; the next stage after 1-8 is 2-1
    clear_until(p, "3-10")  # ... and land IV opens after land III
    c = p.get("/caravan").json()
    assert {r["to"]: r["open"] for r in c["roads"]}["r4_nugush"] is True
    r = p.post("/caravan/travel", {"to": "r4_nugush"})
    assert r.status_code == 200 and r.json()["traveling"] and r.json()["destination"] == "r4_nugush"
    assert r.json()["location_bonus"] == ""  # no local bonus on the road
    assert p.post("/caravan/travel", {"to": "r1_shikhany"}).status_code == 409
    # arrival is settled on access once the time has passed
    from app.models import PlayerCaravan
    gen, db = _db()
    try:
        row = db.get(PlayerCaravan, p.tokens["user_id"])
        row.arrive_at = row.arrive_at - timedelta(hours=5)
        db.commit()
    finally:
        gen.close()
    c = p.get("/caravan").json()
    assert c["location"] == "r4_nugush" and not c["traveling"] and c["trips"] == 1
    assert "эссенции природы" in c["location_bonus"]
