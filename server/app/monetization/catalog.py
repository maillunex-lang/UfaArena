"""Shop catalog: seeding, availability, limits, pricing, personal offers and dynamic contents.

Pricing rules: every discount is computed from the REAL base price stored in the catalog
(no inflated "old" prices); discounts are capped by config (max 35%). Personalisation uses only
the player's roster and resource deficit — never spending history or ability to pay."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..game import data as D
from ..models import (
    CatalogChange, Hero, Order, PlayerCampaignProgress, PlayerHero, PlayerProfile, ShopProduct, User, Wallet,
)
from . import battlepass
from .config import cfg, cosmetic

PAID = ("paid", "fulfilled")


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def seed(db: Session) -> None:
    """Insert products that are missing. Existing rows keep admin edits (price/discount/active)."""
    for p in cfg()["products"]:
        if db.get(ShopProduct, p["sku"]) is not None:
            continue
        meta = {k: p[k] for k in ("unlock_day", "window_days", "repeatable") if k in p}
        db.add(ShopProduct(sku=p["sku"], section=p["section"], name=p["name"], description=p.get("desc", ""),
                           price_rub=p["price_rub"], contents=p["contents"], display=p.get("display", {}),
                           limit=p.get("limit"), meta=meta, starts_at=_dt(p.get("starts")), ends_at=_dt(p.get("ends")),
                           active=True))
    db.flush()


# ------------------------------------------------------------------ limits
def period_start(period: str, product: ShopProduct, now: datetime) -> datetime | None:
    if period == "once":
        return None
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        d = now - timedelta(days=now.weekday())
        return d.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now - timedelta(days=30)
    if period == "season":
        return battlepass.season_bounds(battlepass.season_index(now))[0]
    if period == "event":
        return as_utc(product.starts_at) if product.starts_at else None
    return None


def bought_count(db: Session, user_id: str, product: ShopProduct, now: datetime) -> int:
    lim = product.limit or {}
    q = select(func.count()).select_from(Order).where(Order.user_id == user_id, Order.sku == product.sku,
                                                      Order.status.in_(PAID))
    start = period_start(lim.get("period", "once"), product, now)
    if start is not None:
        q = q.where(Order.paid_at >= start)
    return db.scalar(q) or 0


# ------------------------------------------------------------------ player context
def _ctx(db: Session, user_id: str) -> dict:
    owned = {ph.hero_code: ph for ph in db.scalars(select(PlayerHero).where(PlayerHero.user_id == user_id))}
    cleared = db.scalar(select(func.count()).select_from(PlayerCampaignProgress)
                        .where(PlayerCampaignProgress.user_id == user_id)) or 0
    wallet = {w.currency: w.balance for w in db.scalars(select(Wallet).where(Wallet.user_id == user_id))}
    user = db.get(User, user_id)
    prof = db.get(PlayerProfile, user_id)
    top_level = max([ph.level for ph in owned.values()] or [1])
    return {"owned": owned, "cleared": cleared, "wallet": wallet, "registered": as_utc(user.created_at),
            "profile": prof, "top_level": top_level}


def _unowned(db: Session, ctx: dict, rarity: int) -> str | None:
    for h in db.scalars(select(Hero).where(Hero.is_enemy.is_(False), Hero.summonable.is_(True), Hero.rarity == rarity)
                        .order_by(Hero.code)):
        if h.code not in ctx["owned"]:
            return h.code
    return None


def _deficit(ctx: dict) -> str:
    """Which development resource the player is short of right now."""
    cost = D.level_up_cost(ctx["top_level"])
    w = ctx["wallet"]
    gold_ratio = w.get("gold", 0) / max(cost["gold"], 1)
    nat_ratio = w.get("nature_essence", 0) / max(cost["nature_essence"], 1)
    return "nature_essence" if nat_ratio < gold_ratio else "gold"


def resolve_contents(db: Session, product: ShopProduct, ctx: dict) -> dict:
    c = dict(product.contents or {})
    dyn = c.pop("dynamic", None)
    if not dyn:
        return c
    kind, _, tier_s = dyn.partition(":")
    tier = int(tier_s)
    scale = min(2.0, 1.0 + 0.12 * ctx["cleared"] + 0.02 * ctx["top_level"])
    if kind == "starter":
        table = {
            1: {"currencies": {"crystals": 120, "gold": 20000, "summon_essence": 2}},
            2: {"currencies": {"crystals": 200, "nature_essence": 300, "gold": 30000}, "shards_choice": 10},
            3: {"currencies": {"summon_essence": 3}, "hero_rarity": 3},
            4: {"currencies": {"gold": 80000, "nature_essence": 800, "crystals": 300}},
            5: {"currencies": {"summon_essence": 10, "crystals": 300}},
            6: {"currencies": {"crystals": 500}, "hero_rarity": 4, "cosmetics": ["frame_toratau"]},
            7: {"currencies": {"crystals": 1000, "summon_essence": 10}, "hero_rarity": 5, "cosmetics": ["title_keeper"]},
        }
        out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in table[tier].items()}
        out["currencies"] = {k: int(v * (scale if k in ("gold", "nature_essence") else 1)) for k, v in out["currencies"].items()}
        r = out.pop("hero_rarity", None)
        if r:
            code = _unowned(db, ctx, r)
            if code:
                out["heroes"] = [code]
            else:  # already owns all heroes of that rarity: shards instead
                out["shards_choice"] = 20 * (r - 2)
        return out
    if kind == "resources":
        base = [(15000, 150), (50000, 500), (110000, 1100), (240000, 2400)][tier - 1]
        g, n = base[0] * scale, base[1] * scale
        if _deficit(ctx) == "nature_essence":
            g, n = g * 0.7, n * 1.5
        else:
            g, n = g * 1.4, n * 0.8
        cur = {"gold": int(g), "nature_essence": int(n)}
        if tier >= 3:
            cur["summon_essence"] = tier - 1
        return {"currencies": cur}
    return c


# ------------------------------------------------------------------ availability & price
def personal_offer(product: ShopProduct, ctx: dict) -> tuple[int, str]:
    """(discount %, reason). Uses only roster progress and resource deficit."""
    tiers = cfg()["discounts"]["tiers"]
    if product.section == "heroes" and (product.contents or {}).get("shards_choice"):
        near = [ph for ph in ctx["owned"].values() if ph.shards >= 5 and ph.stars < D.MAX_STARS]
        if near:
            return tiers["small"], "Вашему герою не хватает осколков до новой звезды"
    if product.section == "resources" and product.sku == "resources_1":
        return tiers["small"], "Не хватает ресурсов на развитие героев"
    return 0, ""


def availability(db: Session, product: ShopProduct, user_id: str, ctx: dict, now: datetime) -> tuple[bool, str, datetime | None]:
    if not product.active:
        return False, "inactive", None
    if product.starts_at and now < as_utc(product.starts_at):
        return False, "not_started", as_utc(product.starts_at)
    expires = as_utc(product.ends_at) if product.ends_at else None
    if expires and now >= expires:
        return False, "ended", expires
    meta = product.meta or {}
    if "unlock_day" in meta:
        unlock = ctx["registered"] + timedelta(days=int(meta["unlock_day"]))
        end = ctx["registered"] + timedelta(days=int(meta.get("window_days", 8)))
        if now < unlock:
            return False, "locked_until", unlock
        if now >= end:
            return False, "ended", end
        expires = end
    lim = product.limit or {}
    if lim and bought_count(db, user_id, product, now) >= int(lim.get("count", 1)):
        return False, "limit_reached", expires
    if (product.contents or {}).get("bp_premium") and battlepass.progress(db, user_id).premium:
        return False, "owned", expires
    return True, "", expires


def price_of(product: ShopProduct, ctx: dict) -> tuple[int, int, str]:
    personal, why = personal_offer(product, ctx)
    d = max(int(product.discount_pct or 0), personal)
    d = max(0, min(int(cfg()["discounts"]["max"]), d))
    final = int(round(product.price_rub * (100 - d) / 100 / 100.0)) * 100  # whole rubles
    return final, d, why if personal and personal >= (product.discount_pct or 0) else ""


def view(db: Session, user_id: str, test_mode: bool) -> dict:
    now = utcnow()
    ctx = _ctx(db, user_id)
    items = []
    for p in db.scalars(select(ShopProduct).order_by(ShopProduct.section, ShopProduct.featured.desc(), ShopProduct.price_rub)):
        ok, why, expires = availability(db, p, user_id, ctx, now)
        if not ok and why in ("inactive", "not_started"):
            continue
        final, disc, personal = price_of(p, ctx)
        lim = p.limit or {}
        items.append({
            "sku": p.sku, "section": p.section, "name": p.name, "desc": p.description,
            "price_rub": final, "base_price_rub": p.price_rub, "discount_pct": disc, "personal_reason": personal,
            "contents": resolve_contents(db, p, ctx), "display": p.display or {},
            "limit": lim or None, "bought": bought_count(db, user_id, p, now) if lim else 0,
            "available": ok, "unavailable_reason": why, "expires_at": expires.isoformat() if expires else None,
            "needs_hero_choice": bool((p.contents or {}).get("shards_choice") or (p.contents or {}).get("hero_choice")),
            "hero_choice": (p.contents or {}).get("hero_choice"),
        })
    return {"test_mode": test_mode, "currency": "RUB", "sections": cfg()["sections"], "items": items,
            "server_time": now.isoformat()}


def log_change(db: Session, sku: str, field: str, before, after, actor: str, reason: str = "") -> None:
    db.add(CatalogChange(sku=sku, field=field, before={"v": before}, after={"v": after}, actor=actor, reason=reason))
