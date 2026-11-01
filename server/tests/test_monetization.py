"""Monetization in TEST mode: catalog, full test purchase cycle, no double grants, real payments blocked,
VIP, subscriptions, battle pass, heroes/fragments, cosmetics, lavka, promo codes, refunds, admin, analytics."""
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.models import BattlePassProgress, Order, PlayerProfile, User
from app.monetization import battlepass
from app.monetization.payments import TestProvider
from app.services import ledger_consistent

ADMIN = "admin-token-for-tests-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)
    monkeypatch.delenv("URALIA_PAYMENTS_COMMERCIAL_ALLOWED", raising=False)


def buy(p, sku, hero=None):
    o = p.post("/shop/orders", {"sku": sku, "hero_code": hero})
    assert o.status_code == 200, o.text
    oid = o.json()["order"]["id"]
    c = p.post(f"/shop/orders/{oid}/confirm", {"provider": "test", "payload": {}})
    assert c.status_code == 200, c.text
    return c.json()


def admin_h():
    return {"X-Admin-Token": ADMIN, "X-Admin-Name": "tester"}


def test_catalog_sections_prices_and_test_mode(newplayer):
    p = newplayer()
    d = p.get("/shop").json()
    assert d["test_mode"] is True and d["currency"] == "RUB"
    assert [s[0] for s in d["sections"]] == ["crystals", "resources", "starter", "vip", "heroes", "cosmetics", "battlepass", "seasonal"]
    prices = sorted(i["base_price_rub"] for i in d["items"] if i["section"] == "crystals")
    assert prices == [9900, 29900, 59900, 119000, 239000, 479000]
    subs = {i["sku"]: i["base_price_rub"] for i in d["items"] if i["section"] == "vip"}
    assert subs == {"sub_blessing": 29900, "sub_patronage": 59900}
    starters = {i["sku"]: i for i in d["items"] if i["section"] == "starter"}
    assert starters["starter_1"]["available"] and starters["starter_1"]["base_price_rub"] == 9900
    assert not starters["starter_2"]["available"] and starters["starter_2"]["unavailable_reason"] == "locked_until"
    bp = next(i for i in d["items"] if i["sku"] == "battlepass_premium")
    assert bp["base_price_rub"] == 49900


def test_full_test_purchase_cycle_and_no_double_grant(newplayer):
    p = newplayer()
    before = p.get("/player/me").json()["wallet"]["crystals"]
    o = p.post("/shop/orders", {"sku": "crystals_2"}, key="order-key-123456").json()["order"]
    assert o["status"] == "created" and o["is_test"]
    k = "confirm-key-123456"
    c1 = p.post(f"/shop/orders/{o['id']}/confirm", {"provider": "test"}, key=k).json()
    assert c1["order"]["status"] == "fulfilled" and c1["wallet"]["crystals"] == before + 200
    c2 = p.post(f"/shop/orders/{o['id']}/confirm", {"provider": "test"}, key=k).json()
    assert c2["replayed"] and c2["wallet"]["crystals"] == before + 200
    c3 = p.post(f"/shop/orders/{o['id']}/confirm", {"provider": "test"}).json()  # new key, same order
    assert c3["already"] and c3["wallet"]["crystals"] == before + 200
    hist = p.get("/shop/orders").json()["orders"]
    assert hist[0]["sku"] == "crystals_2" and hist[0]["status"] == "fulfilled"
    vip = p.get("/vip").json()
    assert vip["xp"] >= 299 and vip["level"] >= 1  # 1 VIP XP per ruble (+daily)
    with Session(get_engine()) as db:
        assert ledger_consistent(db, p.tokens["user_id"])


def test_real_payments_blocked_in_test_mode(newplayer, client):
    p = newplayer()
    oid = p.post("/shop/orders", {"sku": "crystals_1"}).json()["order"]["id"]
    for prov in ("rustore", "google_play"):
        r = p.post(f"/shop/orders/{oid}/confirm", {"provider": prov, "payload": {"token": "x"}})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "real_payments_blocked"
    s = client.post("/admin/api/mode", json={"mode": "commercial", "confirm": "нет"}, headers=admin_h())
    assert s.status_code == 409  # env guard + phrase + provider all required
    assert client.get("/api/v1/shop/status").json()["test_mode"] is True


def test_subscription_daily_claim_and_stacking(newplayer):
    p = newplayer()
    buy(p, "sub_blessing")
    subs = {s["code"]: s for s in p.get("/subscriptions").json()["subscriptions"]}
    assert subs["blessing"]["active"] and not subs["patronage"]["active"]
    exp1 = subs["blessing"]["expires_at"]
    r = p.post("/subscriptions/blessing/claim").json()
    assert r["granted"]["currencies"] == {"crystals": 60, "gold": 3000}
    assert p.post("/subscriptions/blessing/claim").status_code == 409
    assert p.post("/subscriptions/patronage/claim").status_code == 403
    buy(p, "sub_blessing")  # stack 30 more days
    exp2 = {s["code"]: s for s in p.get("/subscriptions").json()["subscriptions"]}["blessing"]["expires_at"]
    assert exp2 > exp1
    buy(p, "sub_patronage")  # both can be active together
    assert all(s["active"] for s in p.get("/subscriptions").json()["subscriptions"])
    cos = p.get("/cosmetics").json()["owned"]
    assert {"frame_blessing", "frame_patronage", "title_ancestors_ward"} <= {c["id"] for c in cos}


def test_battlepass_free_premium_retroactive(newplayer):
    p = newplayer()
    with Session(get_engine()) as db:
        row = battlepass.progress(db, p.tokens["user_id"])
        row.xp = 600 * 3
        db.commit()
    bp = p.get("/battlepass").json()
    assert bp["level"] >= 3 and not bp["premium"]
    assert p.post("/battlepass/claim", {"level": 1, "track": "free"}).status_code == 200
    assert p.post("/battlepass/claim", {"level": 1, "track": "free"}).status_code == 409
    assert p.post("/battlepass/claim", {"level": 1, "track": "premium"}).status_code == 403
    assert p.post("/battlepass/claim", {"level": 25, "track": "free"}).status_code == 403
    buy(p, "battlepass_premium")
    for lv in (1, 2, 3):  # already reached levels unlock premium rewards
        assert p.post("/battlepass/claim", {"level": lv, "track": "premium"}).status_code == 200
    assert not next(i for i in p.get("/shop").json()["items"] if i["sku"] == "battlepass_premium")["available"]


def test_battlepass_xp_from_play(newplayer):
    p = newplayer()
    xp0 = p.get("/battlepass").json()["xp"]
    p.post("/battles/validate", {"node_id": "1-1"}, key=False)
    assert p.get("/battlepass").json()["xp"] > xp0


def test_heroes_and_fragments(newplayer):
    p = newplayer()
    assert p.post("/shop/orders", {"sku": "shards_small"}).status_code == 400  # hero choice required
    assert p.post("/shop/orders", {"sku": "shards_small", "hero_code": "morai"}).status_code == 400  # not owned
    r = buy(p, "shards_small", "yurek")
    assert r["order"]["grant"]["shards"] == {"yurek": 5}
    assert p.post("/shop/orders", {"sku": "hero_select_legend", "hero_code": "morai"}).status_code == 400  # mythic not sellable
    r = buy(p, "hero_select_rare", "vargat")
    assert r["order"]["grant"]["heroes"] == ["vargat"]
    codes = {h["hero_code"] for h in p.get("/player/heroes").json()["heroes"]}
    assert "vargat" in codes
    # starter 1 is once
    buy(p, "starter_1")
    assert p.post("/shop/orders", {"sku": "starter_1"}).status_code == 409


def test_shard_bank_unlocks_hero(newplayer):
    from app.monetization import fulfill
    p = newplayer()
    with Session(get_engine()) as db:
        rec = fulfill.grant_contents(db, p.tokens["user_id"], {"shards": {"morai": 25}}, "test", "t")
        db.commit()
        prof = db.get(PlayerProfile, p.tokens["user_id"])
        assert rec["heroes"] == ["morai"] and "morai" not in (prof.hero_shards or {})
        from sqlalchemy import select
        from app.models import PlayerHero
        ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == p.tokens["user_id"], PlayerHero.hero_code == "morai"))
        assert (ph.stars, ph.shards) == (1, 5)  # 25 = 10 unlock + 10 star + 5 shards
        rec2 = fulfill.grant_contents(db, p.tokens["user_id"], {"shards": {"ak_bure": 7}}, "test", "t2")
        db.commit()
        assert "heroes" not in rec2 and db.get(PlayerProfile, p.tokens["user_id"]).hero_shards["ak_bure"] == 7


def test_cosmetics_buy_equip(newplayer):
    p = newplayer()
    assert p.post("/cosmetics/equip", {"slot": "frame", "cosmetic_id": "frame_rift"}, key=False).status_code == 403
    buy(p, "cos_frame_rift")
    buy(p, "cos_skin_morai_void")
    r = p.post("/cosmetics/equip", {"slot": "frame", "cosmetic_id": "frame_rift"}, key=False).json()
    assert r["equipped"]["frame"]["id"] == "frame_rift"
    r = p.post("/cosmetics/equip", {"slot": "hero_skin", "cosmetic_id": "skin_morai_void"}, key=False).json()
    assert r["equipped"]["hero_skins"]["morai"]["id"] == "skin_morai_void"
    boot = p.get("/player/bootstrap").json()
    assert boot["cosmetics"]["frame"]["id"] == "frame_rift" and boot["test_mode"] is True


def test_lavka_crystals_separate_from_real_money(newplayer):
    p = newplayer()
    items = p.get("/shop/lavka").json()["items"]
    assert len(items) == 7 and items == p.get("/shop/lavka").json()["items"]  # deterministic rotation
    it = next(i for i in items if not i["needs_hero_choice"] and "crystals" in i["cost"] and i["cost"]["crystals"] <= 200)
    w0 = p.get("/player/me").json()["wallet"]
    r = p.post(f"/shop/lavka/{it['id']}/buy", {}).json()
    assert r["wallet"]["crystals"] == w0["crystals"] - it["cost"]["crystals"]
    for _ in range(int(it["limit"]) - 1):
        p.post(f"/shop/lavka/{it['id']}/buy", {})
    assert p.post(f"/shop/lavka/{it['id']}/buy", {}).status_code == 409
    assert not p.get("/shop/orders").json()["orders"]  # no real-money orders were created


def test_vip_rewards_and_afk_bonus(newplayer):
    from app.monetization import vip
    p = newplayer()
    with Session(get_engine()) as db:
        vip.add_xp(db, p.tokens["user_id"], 1500, "admin", "t")
        db.commit()
    v = p.get("/vip").json()
    assert v["level"] == 3 and 1 in v["claimable"] and v["battle_speeds"] == [1, 2, 4, 6]
    r = p.post("/vip/rewards/3/claim").json()
    assert "frame_vip3" in r["granted"]["cosmetics"]
    assert p.post("/vip/rewards/3/claim").status_code == 409
    assert p.post("/vip/rewards/5/claim").status_code == 403
    # VIP +4.5% and the starting land Таулар +10% gold (caravan, lore stage S4)
    assert p.get("/rewards/afk").json()["rates_per_hour"]["gold"] == int(600 * 1.045 * 1.10)


def test_refund_via_signed_notification(newplayer, client):
    p = newplayer()
    r = buy(p, "crystals_3")
    txn = None
    with Session(get_engine()) as db:
        txn = db.get(Order, r["order"]["id"]).provider_txn_id
    p.post("/summon", {"pool": "standard_crystals", "count": 1})  # spend part of the crystals
    body = json.dumps({"type": "refund", "provider_txn_id": txn, "reason": "test"}).encode()
    bad = client.post("/api/v1/payments/test/notify", content=body, headers={"X-Uralia-Test-Signature": "x"})
    assert bad.status_code == 400
    ok = client.post("/api/v1/payments/test/notify", content=body,
                     headers={"X-Uralia-Test-Signature": TestProvider.sign(body)}).json()
    assert ok["ok"]
    w = p.get("/player/me").json()["wallet"]
    assert w["crystals"] >= 0
    with Session(get_engine()) as db:
        o = db.get(Order, r["order"]["id"])
        assert o.status == "refunded"
        assert ledger_consistent(db, p.tokens["user_id"])
    again = client.post("/api/v1/payments/test/notify", content=body,
                        headers={"X-Uralia-Test-Signature": TestProvider.sign(body)}).json()
    assert again.get("already")


def test_admin_catalog_promo_analytics(newplayer, client):
    assert client.get("/admin/api/status").status_code == 403
    assert client.get("/admin/api/status", headers={"X-Admin-Token": "wrong-wrong-wrong-wrong-wrong"}).status_code == 403
    h = admin_h()
    assert client.get("/admin/api/status", headers=h).json()["mode"] == "test"
    assert client.patch("/admin/api/products/resources_2", json={"discount_pct": 50}, headers=h).status_code == 422
    assert client.patch("/admin/api/products/resources_2", json={"discount_pct": 20, "reason": "t"}, headers=h).status_code == 200
    p = newplayer()
    item = next(i for i in p.get("/shop").json()["items"] if i["sku"] == "resources_2")
    assert item["discount_pct"] == 20 and item["price_rub"] == 23900 and item["base_price_rub"] == 29900
    ch = client.get("/admin/api/changes", headers=h).json()["changes"][0]
    assert client.post(f"/admin/api/changes/{ch['id']}/revert", headers=h).status_code == 200
    assert next(i for i in p.get("/shop").json()["items"] if i["sku"] == "resources_2")["discount_pct"] == 0
    code = "T" + uuid.uuid4().hex[:8].upper()
    assert client.post("/admin/api/promo", json={"code": code, "rewards": {"currencies": {"crystals": 77}}, "max_uses": 5},
                       headers=h).status_code == 200
    r = p.post("/promo/redeem", {"code": code.lower()}).json()
    assert r["granted"]["currencies"] == {"crystals": 77}
    assert p.post("/promo/redeem", {"code": code}).status_code == 409
    buy(p, "crystals_1")
    a = client.get("/admin/api/analytics", headers=h).json()
    assert a["test_purchases"] >= 1 and a["revenue_rub"] == 0  # test purchases never count as revenue
    assert "crystals:purchase" in a["currency_sources"]
    auto = client.post("/admin/api/analytics/auto-adjust", json={"dry_run": True}, headers=h).json()
    assert auto["limits"]["auto_max"] <= auto["limits"]["max"]
    assert client.get("/admin", headers=h).status_code == 200
