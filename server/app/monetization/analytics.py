"""Shop analytics + bounded assortment automation (owner-defined limits, logged, revertible)."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import (
    AnalyticsEvent, BattlePassProgress, CatalogChange, DailyActivity, Entitlement, Order, PlayerProfile, ShopProduct,
    User, WalletTransaction,
)
from . import battlepass
from .catalog import log_change
from .config import cfg


def track(db: Session, user_id: str | None, event: str, sku: str | None = None, **props) -> None:
    db.add(AnalyticsEvent(user_id=user_id, event=event, sku=sku, props=props))


def summary(db: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    orders = db.scalars(select(Order).where(Order.created_at >= since)).all()
    paid = [o for o in orders if o.status in ("fulfilled", "refunded")]
    real = [o for o in paid if not o.is_test]
    test = [o for o in paid if o.is_test]
    refunds = [o for o in orders if o.status == "refunded"]
    viewers = db.scalar(select(func.count(func.distinct(AnalyticsEvent.user_id)))
                        .where(AnalyticsEvent.event == "shop_view", AnalyticsEvent.created_at >= since)) or 0
    buyers = len({o.user_id for o in paid})
    by_sku: dict = defaultdict(lambda: {"orders": 0, "revenue_rub": 0, "test_orders": 0, "views": 0, "refunds": 0})
    for o in paid:
        s = by_sku[o.sku]
        s["test_orders" if o.is_test else "orders"] += 1
        if not o.is_test and o.status == "fulfilled":
            s["revenue_rub"] += o.price_rub
    for o in refunds:
        by_sku[o.sku]["refunds"] += 1
    for sku, n in db.execute(select(AnalyticsEvent.sku, func.count()).where(AnalyticsEvent.event == "offer_view",
                                                                            AnalyticsEvent.created_at >= since)
                             .group_by(AnalyticsEvent.sku)).all():
        if sku:
            by_sku[sku]["views"] = n
    for s in by_sku.values():
        total = s["orders"] + s["test_orders"]
        s["conversion"] = round(total / s["views"], 3) if s["views"] else None
    sources = {f"{c}:{r.split(':')[0]}": int(v) for c, r, v in db.execute(
        select(WalletTransaction.currency, WalletTransaction.reason, func.sum(WalletTransaction.delta))
        .where(WalletTransaction.delta > 0, WalletTransaction.created_at >= since)
        .group_by(WalletTransaction.currency, WalletTransaction.reason)).all()}
    sinks = {f"{c}:{r.split(':')[0]}": int(-v) for c, r, v in db.execute(
        select(WalletTransaction.currency, WalletTransaction.reason, func.sum(WalletTransaction.delta))
        .where(WalletTransaction.delta < 0, WalletTransaction.created_at >= since)
        .group_by(WalletTransaction.currency, WalletTransaction.reason)).all()}
    now = utcnow()
    subs = db.execute(select(Entitlement.code, func.count()).where(Entitlement.kind == "subscription",
                                                                   Entitlement.revoked_at.is_(None),
                                                                   Entitlement.expires_at > now)
                      .group_by(Entitlement.code)).all()
    vip = dict(db.execute(select(PlayerProfile.vip_level, func.count()).group_by(PlayerProfile.vip_level)).all())
    season = battlepass.season_index()
    bp_total = db.scalar(select(func.count()).select_from(BattlePassProgress).where(BattlePassProgress.season == season)) or 0
    bp_prem = db.scalar(select(func.count()).select_from(BattlePassProgress).where(BattlePassProgress.season == season,
                                                                                  BattlePassProgress.premium.is_(True))) or 0
    return {
        "period_days": days,
        "revenue_rub": sum(o.price_rub for o in real if o.status == "fulfilled"),
        "refunded_rub": sum(o.price_rub for o in refunds if not o.is_test),
        "purchases": len(real), "test_purchases": len(test), "refunds": len(refunds),
        "shop_viewers": viewers, "buyers": buyers, "conversion": round(buyers / viewers, 3) if viewers else None,
        "products": dict(sorted(by_sku.items(), key=lambda kv: -(kv[1]["orders"] + kv[1]["test_orders"]))),
        "vip_distribution": {str(k): v for k, v in vip.items()},
        "subscriptions_active": {c: n for c, n in subs},
        "battlepass": {"season": season, "players": bp_total, "premium": bp_prem},
        "currency_sources": sources, "currency_sinks": sinks,
        "retention": retention(db), "forecast": forecast(db),
        "disputes": db.scalar(select(func.count()).select_from(Order).where(Order.dispute.is_(True))) or 0,
    }


def retention(db: Session) -> dict:
    now = utcnow()
    out = {}
    for d in (1, 7):
        cohort = [u.id for u in db.scalars(select(User).where(User.created_at <= now - timedelta(days=d)))]
        if not cohort:
            out[f"d{d}"] = None
            continue
        back = 0
        for uid in cohort:
            u = db.get(User, uid)
            day = (as_utc(u.created_at) + timedelta(days=d)).strftime("%Y-%m-%d")
            if db.get(DailyActivity, (uid, day)):
                back += 1
        out[f"d{d}"] = round(back / len(cohort), 3)
    return out


def forecast(db: Session) -> dict:
    """Demand forecast: 7-day moving average of paid+test orders per sku -> next 7 days."""
    since = utcnow() - timedelta(days=7)
    rows = db.execute(select(Order.sku, func.count()).where(Order.status == "fulfilled", Order.created_at >= since)
                      .group_by(Order.sku)).all()
    return {sku: {"last_7d": n, "next_7d": round(n / 7 * 7, 1)} for sku, n in rows}


def auto_adjust(db: Session, dry_run: bool = False) -> list[dict]:
    """Within owner limits (discounts.auto_max, auto_allowed_sections): low-conversion products get a
    small discount, top sellers get featured. Every change is logged and revertible."""
    lim = cfg()["discounts"]
    stats = summary(db, 14)["products"]
    changes = []
    for p in db.scalars(select(ShopProduct).where(ShopProduct.section.in_(lim["auto_allowed_sections"]))):
        s = stats.get(p.sku)
        if not s or not s["views"] or s["views"] < 20:
            continue  # not enough data: do nothing
        conv = s["conversion"] or 0
        target = lim["tiers"]["small"] if conv < 0.02 else 0
        target = min(target, lim["auto_max"])
        if target != (p.discount_pct or 0):
            changes.append({"sku": p.sku, "field": "discount_pct", "before": p.discount_pct, "after": target,
                            "reason": f"conversion {conv:.3f} over {s['views']} views"})
            if not dry_run:
                log_change(db, p.sku, "discount_pct", p.discount_pct, target, "auto", changes[-1]["reason"])
                p.discount_pct = target
    if not dry_run:
        db.commit()
    return changes


def revert_change(db: Session, change_id: int, actor: str) -> dict:
    ch = db.get(CatalogChange, change_id)
    if ch is None or ch.reverted:
        raise ValueError("change not found or already reverted")
    p = db.get(ShopProduct, ch.sku)
    cur = getattr(p, ch.field)
    setattr(p, ch.field, ch.before["v"])
    ch.reverted = True
    log_change(db, ch.sku, ch.field, cur, ch.before["v"], actor, f"revert #{change_id}")
    db.commit()
    return {"sku": ch.sku, "field": ch.field, "value": ch.before["v"]}
