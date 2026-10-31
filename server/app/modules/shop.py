"""Shop, payments (test mode by default), VIP, subscriptions, battle pass, cosmetics, promo codes.

Real-money products and in-game-currency purchases are separated technically:
  /shop/orders*   real-money catalog -> order -> provider verification -> server grant
  /shop/lavka*    daily/weekly items for crystals / ancient seals (wallet ledger)
In TEST mode the server only accepts the test provider; no payment system is ever contacted.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import (
    Entitlement, Hero, LavkaPurchase, Order, PlayerHero, PlayerProfile, PromoCode, PromoRedemption, ShopProduct,
    SubscriptionClaim, VipRewardClaim,
)
from ..monetization import analytics, battlepass, catalog, fulfill, vip
from ..monetization.config import cfg, cosmetic
from ..monetization.mode import get_mode, is_test
from ..monetization.payments import PROVIDERS, PaymentError
from ..services import spend, wallet_dict

router = APIRouter(tags=["shop"])


def _profile_extras(db: Session, user_id: str) -> dict:
    return {"wallet": wallet_dict(db, user_id)}


# ------------------------------------------------------------------ catalog
@router.get("/shop")
def shop(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    catalog.seed(db)
    out = catalog.view(db, user.id, is_test(db))
    analytics.track(db, user.id, "shop_view")
    db.commit()
    return out


class ViewIn(BaseModel):
    skus: list[str] = Field(default_factory=list, max_length=60)


@router.post("/shop/offer-view")
def offer_view(body: ViewIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Batched offer impressions (one request per shop section render)."""
    for sku in body.skus:
        analytics.track(db, user.id, "offer_view", sku[:64])
    db.commit()
    return {"ok": True, "tracked": len(body.skus)}


class OrderIn(BaseModel):
    sku: str = Field(max_length=64)
    hero_code: str | None = Field(default=None, max_length=48)


def _order_view(o: Order) -> dict:
    return {"id": o.id, "sku": o.sku, "section": o.section, "status": o.status, "provider": o.provider,
            "is_test": o.is_test, "price_rub": o.price_rub, "base_price_rub": o.base_price_rub,
            "discount_pct": o.discount_pct, "grant": o.grant, "created_at": as_utc(o.created_at).isoformat(),
            "fulfilled_at": as_utc(o.fulfilled_at).isoformat() if o.fulfilled_at else None,
            "refunded_at": as_utc(o.refunded_at).isoformat() if o.refunded_at else None}


def _validate_choice(db: Session, user_id: str, contents: dict, hero_code: str | None) -> None:
    if contents.get("shards_choice"):
        ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == user_id, PlayerHero.hero_code == (hero_code or "")))
        if ph is None:
            raise GameError("hero_choice_required", "Выберите героя из своей коллекции")
    if contents.get("hero_choice"):
        h = db.get(Hero, hero_code or "")
        if h is None or h.is_enemy or not h.summonable or h.rarity > int(contents["hero_choice"]["rarity_max"]):
            raise GameError("hero_choice_invalid", "Этого героя нельзя выбрать в данном наборе")


@router.post("/shop/orders")
def create_order(body: OrderIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                 db: Session = Depends(get_db)):
    def do():
        catalog.seed(db)
        p = db.get(ShopProduct, body.sku)
        if p is None:
            raise GameError("not_found", "Товар не найден", 404)
        now = utcnow()
        ctx = catalog._ctx(db, user.id)
        ok, why, _ = catalog.availability(db, p, user.id, ctx, now)
        if not ok:
            raise GameError("unavailable", f"Товар недоступен ({why})", 409)
        contents = catalog.resolve_contents(db, p, ctx)
        _validate_choice(db, user.id, contents, body.hero_code)
        final, disc, _why = catalog.price_of(p, ctx)
        test = is_test(db)
        o = Order(user_id=user.id, sku=p.sku, section=p.section, status="created", provider="test" if test else "pending",
                  is_test=test, base_price_rub=p.price_rub, price_rub=final, discount_pct=disc,
                  params={"hero_code": body.hero_code, "contents": contents})
        db.add(o)
        db.flush()
        analytics.track(db, user.id, "purchase_started", p.sku, price=final, test=test)
        audit(db, user.id, "shop.order_created", sku=p.sku, order=o.id, test=test)
        return {"order": _order_view(o), "test_mode": test,
                "provider_hint": "test" if test else "rustore|google_play"}

    return run_idempotent(db, user.id, key, "shop_order", body.model_dump(), do)


class ConfirmIn(BaseModel):
    provider: str = Field(default="test", max_length=16)
    payload: dict = Field(default_factory=dict)  # store purchase token / receipt for real providers


def _fulfill(db: Session, o: Order) -> None:
    contents = (o.params or {}).get("contents") or {}
    rec = fulfill.grant_contents(db, o.user_id, contents, f"purchase:{o.sku}", o.id, o.params, o.id)
    xp = int(cfg()["vip"]["xp_per_rub"] * o.price_rub / 100)
    if xp:
        vip.add_xp(db, o.user_id, xp, "purchase_test" if o.is_test else "purchase", o.id)
        rec["vip_xp"] = xp
    o.grant = rec
    o.status, o.fulfilled_at = "fulfilled", utcnow()


@router.post("/shop/orders/{order_id}/confirm")
def confirm_order(order_id: str, body: ConfirmIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                  db: Session = Depends(get_db)):
    def do():
        o = db.get(Order, order_id, with_for_update=True)
        if o is None or o.user_id != user.id:
            raise GameError("not_found", "Заказ не найден", 404)
        if o.status == "fulfilled":
            return {"order": _order_view(o), "wallet": wallet_dict(db, user.id), "already": True}
        if o.status != "created":
            raise GameError("bad_state", f"Заказ в состоянии {o.status}", 409)
        test = is_test(db)
        prov = PROVIDERS.get(body.provider)
        if prov is None:
            raise GameError("bad_provider", "Неизвестный платёжный провайдер")
        if test and body.provider != "test":
            raise GameError("real_payments_blocked", "Тестовый режим: реальные платежи заблокированы сервером", 403)
        if not test and body.provider == "test":
            raise GameError("test_disabled", "Тестовые покупки отключены", 403)
        try:
            txn = prov.verify_purchase(o, body.payload, test)
        except PaymentError as e:
            o.status = "failed"
            o.note = e.message
            db.commit()
            raise GameError(e.code, e.message, 402)
        if db.scalar(select(Order).where(Order.provider_txn_id == txn, Order.id != o.id)):
            raise GameError("duplicate_transaction", "Транзакция уже использована", 409)
        o.provider, o.provider_txn_id, o.status, o.paid_at = body.provider, txn, "paid", utcnow()
        _fulfill(db, o)
        analytics.track(db, user.id, "purchase_completed", o.sku, price=o.price_rub, test=o.is_test)
        audit(db, user.id, "shop.order_fulfilled", order=o.id, sku=o.sku, test=o.is_test)
        return {"order": _order_view(o), "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, f"shop_confirm:{order_id}", body.model_dump(), do)


@router.get("/shop/orders")
def orders(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    rows = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(50))
    return {"orders": [_order_view(o) for o in rows]}


def process_refund(db: Session, o: Order, actor: str, reason: str = "") -> dict:
    """Refund: reverse the grant without negative balances; leftovers become a dispute for admins."""
    if o.status == "refunded":
        return {"already": True}
    if o.status != "fulfilled":
        raise GameError("bad_state", "Возврат возможен только для выданного заказа", 409)
    debt = fulfill.revoke(db, o.user_id, o.grant or {}, f"refund:{o.sku}", o.id)
    xp = int((o.grant or {}).get("vip_xp", 0))
    if xp:
        vip.add_xp(db, o.user_id, -xp, "refund", o.id)
    if (o.grant or {}).get("bp_premium") is not None:
        row = battlepass.progress(db, o.user_id)
        if row.claimed_premium:
            debt["bp_premium_claimed_levels"] = list(row.claimed_premium)
    o.status, o.refunded_at, o.refund_debt = "refunded", utcnow(), debt
    o.dispute = bool(debt)
    o.note = (o.note + f" | refund by {actor}: {reason}").strip(" |")
    analytics.track(db, o.user_id, "refund", o.sku, price=o.price_rub, test=o.is_test)
    audit(db, o.user_id, "shop.refund", order=o.id, actor=actor, debt=debt)
    return {"order": o.id, "debt": debt, "dispute": o.dispute}


@router.post("/payments/{provider}/notify")
async def payment_notify(provider: str, request: Request, db: Session = Depends(get_db)):
    """Payment system notifications (refunds/chargebacks). Signature verified by the provider adapter."""
    prov = PROVIDERS.get(provider)
    if prov is None:
        raise GameError("not_found", "Неизвестный провайдер", 404)
    body = await request.body()
    try:
        note = prov.parse_notification({k.lower(): v for k, v in request.headers.items()}, body)
    except PaymentError as e:
        raise GameError(e.code, e.message, 400 if e.code == "bad_signature" else 501)
    o = db.scalar(select(Order).where(Order.provider_txn_id == note.get("provider_txn_id", "")))
    if o is None:
        raise GameError("not_found", "Заказ не найден", 404)
    if note.get("type") == "refund":
        res = process_refund(db, o, f"provider:{provider}", note.get("reason", ""))
        db.commit()
        return {"ok": True, **res}
    return {"ok": True, "ignored": note.get("type")}


# ------------------------------------------------------------------ lavka (in-game currency)
def _periods() -> dict:
    now = utcnow()
    y, w, _ = now.isocalendar()
    return {"daily": f"d:{now:%Y-%m-%d}", "weekly": f"w:{y}-{w:02d}"}


def _rotation(user_id: str, pool: list, slots: int, period: str) -> list:
    """Deterministic per-player rotation that refreshes each day/week (no artificial resets)."""
    ranked = sorted(pool, key=lambda it: hashlib.sha256(f"{user_id}:{period}:{it['id']}".encode()).hexdigest())
    return ranked[:slots]


def _lavka_items(db: Session, user_id: str) -> list:
    lv = cfg()["lavka"]
    per = _periods()
    out = []
    for kind, slots in (("daily", lv["daily_slots"]), ("weekly", lv["weekly_slots"])):
        for it in _rotation(user_id, lv[f"{kind}_pool"], slots, per[kind]):
            row = db.get(LavkaPurchase, (user_id, per[kind], it["id"]))
            out.append({**it, "kind": kind, "period": per[kind], "bought": row.count if row else 0,
                        "needs_hero_choice": bool(it["contents"].get("shards_choice"))})
    return out


@router.get("/shop/lavka")
def lavka(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    now = utcnow()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = (now + timedelta(days=7 - now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"items": _lavka_items(db, user.id), "daily_refresh": tomorrow.isoformat(), "weekly_refresh": monday.isoformat()}


class LavkaIn(BaseModel):
    hero_code: str | None = Field(default=None, max_length=48)


@router.post("/shop/lavka/{item_id}/buy")
def lavka_buy(item_id: str, body: LavkaIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
              db: Session = Depends(get_db)):
    def do():
        item = next((i for i in _lavka_items(db, user.id) if i["id"] == item_id), None)
        if item is None:
            raise GameError("not_in_rotation", "Товара нет в текущей ротации", 404)
        row = db.get(LavkaPurchase, (user.id, item["period"], item_id), with_for_update=True)
        if row is None:
            row = LavkaPurchase(user_id=user.id, period=item["period"], item_id=item_id, count=0)
            db.add(row)
        if row.count >= int(item["limit"]):
            raise GameError("limit_reached", "Лимит покупок исчерпан до обновления", 409)
        _validate_choice(db, user.id, item["contents"], body.hero_code)
        spend(db, user.id, item["cost"], f"lavka:{item_id}", item["period"])
        rec = fulfill.grant_contents(db, user.id, item["contents"], f"lavka:{item_id}", item["period"],
                                     {"hero_code": body.hero_code})
        row.count += 1
        analytics.track(db, user.id, "lavka_buy", item_id, cost=item["cost"])
        return {"granted": rec, "wallet": wallet_dict(db, user.id), "bought": row.count}

    return run_idempotent(db, user.id, key, f"lavka:{item_id}", body.model_dump(), do)


# ------------------------------------------------------------------ VIP
@router.get("/vip")
def vip_view(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return vip.view(db, user.id)


@router.post("/vip/rewards/{level}/claim")
def vip_claim(level: int, user: CurrentUser = Depends(player), key: str = Depends(require_key),
              db: Session = Depends(get_db)):
    def do():
        p = db.get(PlayerProfile, user.id)
        if level < 1 or level > (p.vip_level or 0):
            raise GameError("vip_locked", "Уровень VIP ещё не достигнут", 403)
        if db.get(VipRewardClaim, (user.id, level)):
            raise GameError("already_claimed", "Награда уже получена", 409)
        db.add(VipRewardClaim(user_id=user.id, level=level))
        rec = fulfill.grant_contents(db, user.id, cfg()["vip"]["rewards"][str(level)], "vip_reward", str(level))
        return {"granted": rec, "wallet": wallet_dict(db, user.id), "vip": vip.view(db, user.id)}

    return run_idempotent(db, user.id, key, f"vip_claim:{level}", {}, do)


# ------------------------------------------------------------------ subscriptions
def _active_subs(db: Session, user_id: str) -> dict:
    now = utcnow()
    out = {}
    for e in db.scalars(select(Entitlement).where(Entitlement.user_id == user_id, Entitlement.kind == "subscription",
                                                  Entitlement.revoked_at.is_(None))):
        if e.expires_at and as_utc(e.starts_at) <= now < as_utc(e.expires_at):
            out[e.code] = max(out.get(e.code, now), as_utc(e.expires_at))
        elif e.expires_at and as_utc(e.starts_at) > now:  # stacked future period
            out[e.code] = max(out.get(e.code, now), as_utc(e.expires_at))
    return out


@router.get("/subscriptions")
def subscriptions(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    active = _active_subs(db, user.id)
    day = utcnow().strftime("%Y-%m-%d")
    out = []
    for code, sub in cfg()["subscriptions"].items():
        claimed = db.get(SubscriptionClaim, (user.id, code, day)) is not None
        out.append({"code": code, "name": sub["name"], "active": code in active,
                    "expires_at": active[code].isoformat() if code in active else None,
                    "daily": sub["daily"], "claimed_today": claimed, "cosmetics": sub.get("cosmetics", []),
                    "effects": sub.get("effects", []), "on_purchase": sub.get("on_purchase", {}),
                    "sku": f"sub_{code}"})
    return {"subscriptions": out}


@router.post("/subscriptions/{code}/claim")
def subscription_claim(code: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                       db: Session = Depends(get_db)):
    def do():
        sub = cfg()["subscriptions"].get(code)
        if sub is None:
            raise GameError("not_found", "Подписка не найдена", 404)
        if code not in _active_subs(db, user.id):
            raise GameError("not_active", "Подписка не активна", 403)
        day = utcnow().strftime("%Y-%m-%d")
        if db.get(SubscriptionClaim, (user.id, code, day)):
            raise GameError("already_claimed", "Сегодняшняя награда уже получена", 409)
        db.add(SubscriptionClaim(user_id=user.id, code=code, day=day, rewards=sub["daily"]))
        rec = fulfill.grant_contents(db, user.id, {"currencies": sub["daily"]}, f"subscription:{code}", day)
        return {"granted": rec, "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, f"sub_claim:{code}:{utcnow():%Y-%m-%d}", {}, do)


# ------------------------------------------------------------------ battle pass
@router.get("/battlepass")
def battlepass_view(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    out = battlepass.view(db, user.id)
    db.commit()
    return out


class BpClaimIn(BaseModel):
    level: int = Field(ge=1, le=200)
    track: str = Field(pattern="^(free|premium)$")


@router.post("/battlepass/claim")
def battlepass_claim(body: BpClaimIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                     db: Session = Depends(get_db)):
    def do():
        row = battlepass.progress(db, user.id, lock=True)
        if body.level > battlepass.level_of(row.xp):
            raise GameError("bp_locked", "Уровень пропуска ещё не достигнут", 403)
        if body.track == "premium" and not row.premium:
            raise GameError("bp_premium_required", "Нужна Premium-линия", 403)
        claimed = list(row.claimed_free if body.track == "free" else row.claimed_premium)
        if body.level in claimed:
            raise GameError("already_claimed", "Награда уже получена", 409)
        lvl = next(x for x in cfg()["battlepass"]["levels"] if x["level"] == body.level)
        claimed.append(body.level)
        if body.track == "free":
            row.claimed_free = claimed
        else:
            row.claimed_premium = claimed
        rec = fulfill.grant_contents(db, user.id, lvl[body.track], f"battlepass:{body.track}", f"{row.season}:{body.level}")
        return {"granted": rec, "wallet": wallet_dict(db, user.id), "battlepass": battlepass.view(db, user.id)}

    return run_idempotent(db, user.id, key, f"bp_claim:{body.level}:{body.track}", body.model_dump(), do)


# ------------------------------------------------------------------ cosmetics
SLOTS = {"frame": "frame", "title": "title", "profile_effect": "profile_effect", "emote": "emote",
         "fortress": "fortress", "hero_skin": "hero_skins", "ability_effect": "ability_effects"}


def owned_cosmetics(db: Session, user_id: str) -> set[str]:
    now = utcnow()
    out = set()
    for e in db.scalars(select(Entitlement).where(Entitlement.user_id == user_id, Entitlement.kind == "cosmetic",
                                                  Entitlement.revoked_at.is_(None))):
        if e.expires_at is None or as_utc(e.starts_at) <= now < as_utc(e.expires_at):
            out.add(e.code)
    return out


def equipped_view(db: Session, user_id: str) -> dict:
    """Equipped cosmetics, filtered to what the player currently owns (expired subscription items drop)."""
    p = db.get(PlayerProfile, user_id)
    own = owned_cosmetics(db, user_id)
    eq = dict(p.cosmetics or {})
    out = {}
    for slot, val in eq.items():
        if isinstance(val, dict):
            out[slot] = {k: v for k, v in val.items() if v in own}
        elif val in own:
            out[slot] = val
    resolved = {}
    for slot, val in out.items():
        if isinstance(val, dict):
            resolved[slot] = {k: cosmetic(v) for k, v in val.items()}
        else:
            resolved[slot] = cosmetic(val)
    return resolved


@router.get("/cosmetics")
def cosmetics(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    own = owned_cosmetics(db, user.id)
    return {"owned": [c for c in cfg()["cosmetics"] if c["id"] in own], "equipped": equipped_view(db, user.id),
            "raw": db.get(PlayerProfile, user.id).cosmetics or {}}


class EquipIn(BaseModel):
    cosmetic_id: str | None = Field(default=None, max_length=64)
    slot: str = Field(max_length=24)
    hero: str | None = Field(default=None, max_length=48)


@router.post("/cosmetics/equip")
def equip(body: EquipIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if body.slot not in SLOTS:
        raise GameError("bad_slot", "Неизвестный слот")
    p = db.get(PlayerProfile, user.id)
    eq = dict(p.cosmetics or {})
    key = SLOTS[body.slot]
    if body.cosmetic_id:
        c = cosmetic(body.cosmetic_id)
        if c is None or c["type"] != body.slot:
            raise GameError("bad_cosmetic", "Предмет не подходит для слота")
        if body.cosmetic_id not in owned_cosmetics(db, user.id):
            raise GameError("not_owned", "Предмет не принадлежит игроку", 403)
        if key in ("hero_skins", "ability_effects"):
            hero = (c.get("data") or {}).get("hero") or body.hero
            if not hero:
                raise GameError("hero_required", "Укажите героя")
            m = dict(eq.get(key) or {})
            m[hero] = body.cosmetic_id
            eq[key] = m
        else:
            eq[key] = body.cosmetic_id
    else:
        if key in ("hero_skins", "ability_effects") and body.hero:
            m = dict(eq.get(key) or {})
            m.pop(body.hero, None)
            eq[key] = m
        else:
            eq.pop(key, None)
    p.cosmetics = eq
    db.commit()
    return {"equipped": equipped_view(db, user.id)}


# ------------------------------------------------------------------ promo codes
class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)


@router.post("/promo/redeem")
def promo_redeem(body: PromoIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                 db: Session = Depends(get_db)):
    def do():
        code = body.code.strip().upper()
        pc = db.get(PromoCode, code, with_for_update=True)
        now = utcnow()
        if pc is None or not pc.active or (pc.starts_at and now < as_utc(pc.starts_at)) or (pc.ends_at and now >= as_utc(pc.ends_at)):
            raise GameError("promo_invalid", "Промокод недействителен", 404)
        if pc.max_uses and pc.uses >= pc.max_uses:
            raise GameError("promo_exhausted", "Промокод исчерпан", 409)
        if db.get(PromoRedemption, (code, user.id)):
            raise GameError("promo_used", "Вы уже активировали этот промокод", 409)
        db.add(PromoRedemption(code=code, user_id=user.id))
        pc.uses += 1
        rec = fulfill.grant_contents(db, user.id, pc.rewards, "promo", code)
        analytics.track(db, user.id, "promo_redeem", code)
        return {"granted": rec, "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, "promo", {"code": body.code.strip().upper()}, do)


@router.get("/shop/status")
def shop_status(db: Session = Depends(get_db)):
    return {"mode": get_mode(db), "test_mode": is_test(db)}
