"""Owner/admin API for monetization. Disabled unless URALIA_ADMIN_TOKEN (>= 24 chars) is set.
Every write is recorded in admin_actions (and catalog_changes for catalog edits, revertible)."""
from __future__ import annotations

import hmac
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ratelimit
from ..core.db import as_utc, get_db
from ..core.errors import GameError
from ..models import AdminAction, CatalogChange, Order, PlayerProfile, PromoCode, ShopProduct
from ..monetization import analytics, catalog, vip
from ..monetization.config import cfg
from ..monetization.mode import CONFIRM_PHRASE, ModeError, get_mode, set_mode
from ..monetization.payments import status as provider_status
from .shop import _order_view, process_refund

router = APIRouter(prefix="/admin/api", tags=["admin"])
page = APIRouter(tags=["admin"])


def admin(request: Request, x_admin_token: str | None = Header(default=None),
          x_admin_name: str | None = Header(default=None)) -> str:
    ratelimit.hit(f"admin:{ratelimit.client_ip(request)}", 60)
    expected = os.environ.get("URALIA_ADMIN_TOKEN", "")
    if len(expected) < 24:
        raise GameError("admin_disabled", "Админ-панель отключена (не задан URALIA_ADMIN_TOKEN)", 403)
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise GameError("forbidden", "Неверный токен администратора", 403)
    from urllib.parse import unquote
    return unquote(x_admin_name or "owner")[:48]


def _log(db: Session, who: str, action: str, **details) -> None:
    db.add(AdminAction(admin=who, action=action, details=details))


@router.get("/status")
def status(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"mode": get_mode(db), "providers": provider_status(), "confirm_phrase": CONFIRM_PHRASE,
            "commercial_env_allowed": os.environ.get("URALIA_PAYMENTS_COMMERCIAL_ALLOWED") == "1"}


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(test|commercial)$")
    confirm: str = ""


@router.post("/mode")
def mode(body: ModeIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        return {"mode": set_mode(db, body.mode, who, body.confirm)}
    except ModeError as e:
        raise GameError("mode_refused", str(e), 409)


@router.get("/products")
def products(who: str = Depends(admin), db: Session = Depends(get_db)):
    catalog.seed(db)
    db.commit()
    return {"products": [{"sku": p.sku, "section": p.section, "name": p.name, "price_rub": p.price_rub,
                          "discount_pct": p.discount_pct, "active": p.active, "limit": p.limit, "featured": p.featured,
                          "starts_at": as_utc(p.starts_at).isoformat() if p.starts_at else None,
                          "ends_at": as_utc(p.ends_at).isoformat() if p.ends_at else None}
                         for p in db.scalars(select(ShopProduct).order_by(ShopProduct.section, ShopProduct.price_rub))]}


class ProductPatch(BaseModel):
    price_rub: int | None = Field(default=None, ge=100, le=10_000_000)  # kopecks: 1 ₽ .. 100 000 ₽
    discount_pct: int | None = Field(default=None, ge=0, le=100)
    active: bool | None = None
    featured: int | None = None
    limit: dict | None = None
    ends_at: datetime | None = None
    reason: str = ""


@router.patch("/products/{sku}")
def patch_product(sku: str, body: ProductPatch, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = db.get(ShopProduct, sku)
    if p is None:
        raise GameError("not_found", "Товар не найден", 404)
    if body.discount_pct is not None and body.discount_pct > cfg()["discounts"]["max"]:
        raise GameError("discount_cap", f"Скидка не больше {cfg()['discounts']['max']}%", 422)
    for field in ("price_rub", "discount_pct", "active", "featured", "limit", "ends_at"):
        val = getattr(body, field)
        if val is None:
            continue
        before = getattr(p, field)
        catalog.log_change(db, sku, field, before.isoformat() if isinstance(before, datetime) else before,
                           val.isoformat() if isinstance(val, datetime) else val, f"admin:{who}", body.reason)
        setattr(p, field, val)
    _log(db, who, "catalog.patch", sku=sku, changes=body.model_dump(exclude_none=True, mode="json"))
    db.commit()
    return {"ok": True}


@router.get("/changes")
def changes(who: str = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(CatalogChange).order_by(CatalogChange.id.desc()).limit(200))
    return {"changes": [{"id": c.id, "sku": c.sku, "field": c.field, "before": c.before.get("v"), "after": c.after.get("v"),
                         "actor": c.actor, "reason": c.reason, "reverted": c.reverted,
                         "at": as_utc(c.created_at).isoformat()} for c in rows]}


@router.post("/changes/{change_id}/revert")
def revert(change_id: int, who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        res = analytics.revert_change(db, change_id, f"admin:{who}")
    except ValueError as e:
        raise GameError("bad_change", str(e), 409)
    _log(db, who, "catalog.revert", change=change_id)
    db.commit()
    return res


@router.get("/orders")
def orders(status: str | None = None, dispute: bool | None = None, who: str = Depends(admin),
           db: Session = Depends(get_db)):
    q = select(Order).order_by(Order.created_at.desc()).limit(200)
    if status:
        q = q.where(Order.status == status)
    if dispute is not None:
        q = q.where(Order.dispute.is_(dispute))
    return {"orders": [dict(_order_view(o), user_id=o.user_id, refund_debt=o.refund_debt, dispute=o.dispute,
                            note=o.note, provider_txn_id=o.provider_txn_id) for o in db.scalars(q)]}


class RefundIn(BaseModel):
    reason: str = ""


@router.post("/orders/{order_id}/refund")
def refund(order_id: str, body: RefundIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    o = db.get(Order, order_id, with_for_update=True)
    if o is None:
        raise GameError("not_found", "Заказ не найден", 404)
    res = process_refund(db, o, f"admin:{who}", body.reason)
    _log(db, who, "order.refund", order=order_id, reason=body.reason)
    db.commit()
    return res


class ResolveIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


@router.post("/orders/{order_id}/resolve")
def resolve(order_id: str, body: ResolveIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if o is None:
        raise GameError("not_found", "Заказ не найден", 404)
    o.dispute = False
    o.note = (o.note + f" | resolved by {who}: {body.note}").strip(" |")
    _log(db, who, "order.resolve", order=order_id, note=body.note)
    db.commit()
    return {"ok": True}


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    rewards: dict
    max_uses: int = Field(default=0, ge=0)
    ends_at: datetime | None = None


@router.post("/promo")
def promo_create(body: PromoIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    code = body.code.upper()
    if db.get(PromoCode, code):
        raise GameError("exists", "Промокод уже существует", 409)
    allowed = {"currencies", "shards", "cosmetics"}
    if not set(body.rewards) <= allowed:
        raise GameError("bad_rewards", f"Разрешены только {sorted(allowed)}", 422)
    db.add(PromoCode(code=code, rewards=body.rewards, max_uses=body.max_uses, ends_at=body.ends_at, created_by=who))
    _log(db, who, "promo.create", code=code, rewards=body.rewards, max_uses=body.max_uses)
    db.commit()
    return {"ok": True, "code": code}


@router.get("/promo")
def promo_list(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"promo": [{"code": p.code, "rewards": p.rewards, "uses": p.uses, "max_uses": p.max_uses, "active": p.active,
                       "ends_at": as_utc(p.ends_at).isoformat() if p.ends_at else None}
                      for p in db.scalars(select(PromoCode).order_by(PromoCode.created_at.desc()))]}


@router.post("/promo/{code}/disable")
def promo_disable(code: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = db.get(PromoCode, code.upper())
    if p is None:
        raise GameError("not_found", "Нет такого промокода", 404)
    p.active = False
    _log(db, who, "promo.disable", code=p.code)
    db.commit()
    return {"ok": True}


@router.get("/analytics")
def analytics_view(days: int = 30, who: str = Depends(admin), db: Session = Depends(get_db)):
    return analytics.summary(db, days)


class AutoIn(BaseModel):
    dry_run: bool = True


@router.post("/analytics/auto-adjust")
def auto_adjust(body: AutoIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    res = analytics.auto_adjust(db, body.dry_run)
    _log(db, who, "catalog.auto_adjust", dry_run=body.dry_run, changes=res)
    db.commit()
    return {"changes": res, "dry_run": body.dry_run, "limits": cfg()["discounts"]}


class VipIn(BaseModel):
    uralia_id: str
    delta_xp: int


@router.post("/vip")
def vip_adjust(body: VipIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    p = db.scalar(select(PlayerProfile).where(PlayerProfile.uralia_id == body.uralia_id))
    if p is None:
        raise GameError("not_found", "Игрок не найден", 404)
    lv = vip.add_xp(db, p.user_id, body.delta_xp, "admin", who)
    _log(db, who, "vip.adjust", uralia_id=body.uralia_id, delta=body.delta_xp)
    db.commit()
    return {"vip_level": lv, "vip_xp": p.vip_xp}


@page.get("/admin/shop", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse((Path(__file__).resolve().parents[1] / "monetization" / "admin.html").read_text(encoding="utf-8"))
