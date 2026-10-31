"""Granting purchased contents (server-side only) and revoking them on refunds.

Every grant returns an exact record stored on the order, so a refund can reverse precisely
what was given. Currency changes go through the immutable wallet ledger."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..game import data as D
from ..models import Entitlement, Hero, PlayerHero, PlayerProfile, Wallet
from ..services import apply_delta, grant as wallet_grant, quest_event
from . import battlepass
from .config import cfg, cosmetic

SHARDS_PER_HERO = 10


def _add_shards(db: Session, user_id: str, code: str, n: int, rec: dict) -> None:
    ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == user_id, PlayerHero.hero_code == code))
    if ph is not None:
        ph.shards += n
        while ph.shards >= D.SHARDS_PER_STAR and ph.stars < D.MAX_STARS:
            ph.shards -= D.SHARDS_PER_STAR
            ph.stars += 1
        rec.setdefault("shards", {})[code] = rec.get("shards", {}).get(code, 0) + n
        return
    # accumulate shards of a not-yet-owned hero; 10 shards unlock the hero
    p = db.get(PlayerProfile, user_id, with_for_update=True)
    bank = dict(p.hero_shards or {})
    bank[code] = bank.get(code, 0) + n
    rec.setdefault("hero_bank", {})[code] = rec.get("hero_bank", {}).get(code, 0) + n
    if bank[code] >= SHARDS_PER_HERO:
        rest = bank.pop(code) - SHARDS_PER_HERO
        ph = PlayerHero(user_id=user_id, hero_code=code, level=1, stars=0, shards=rest)
        while ph.shards >= D.SHARDS_PER_STAR and ph.stars < D.MAX_STARS:  # extra shards go to the new hero
            ph.shards -= D.SHARDS_PER_STAR
            ph.stars += 1
        db.add(ph)
        rec.setdefault("heroes", []).append(code)
    p.hero_shards = bank
    db.flush()


def _add_hero(db: Session, user_id: str, code: str, rec: dict) -> None:
    ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == user_id, PlayerHero.hero_code == code))
    if ph is None:
        db.add(PlayerHero(user_id=user_id, hero_code=code))
        db.flush()
        rec.setdefault("heroes", []).append(code)
    else:  # duplicate -> development currency (shards), never a loss
        _add_shards(db, user_id, code, SHARDS_PER_HERO, rec)


def _entitle(db: Session, user_id: str, kind: str, code: str, days: int | None, order_id: str | None,
             source: str, rec: dict) -> Entitlement:
    now = utcnow()
    ent = None
    if days:
        cur = db.scalars(select(Entitlement).where(Entitlement.user_id == user_id, Entitlement.kind == kind,
                                                   Entitlement.code == code, Entitlement.revoked_at.is_(None))
                         .order_by(Entitlement.expires_at.desc())).first()
        start = max(now, as_utc(cur.expires_at)) if cur and cur.expires_at and as_utc(cur.expires_at) > now else now
        ent = Entitlement(user_id=user_id, kind=kind, code=code, starts_at=start, expires_at=start + timedelta(days=days),
                          order_id=order_id, source=source)
    else:
        if db.scalar(select(Entitlement).where(Entitlement.user_id == user_id, Entitlement.kind == kind,
                                               Entitlement.code == code, Entitlement.revoked_at.is_(None),
                                               Entitlement.expires_at.is_(None))):
            return None  # already owned permanently
        ent = Entitlement(user_id=user_id, kind=kind, code=code, order_id=order_id, source=source)
    db.add(ent)
    db.flush()
    rec.setdefault("entitlements", []).append(ent.id)
    return ent


def grant_contents(db: Session, user_id: str, contents: dict, reason: str, ref: str | None = None,
                   params: dict | None = None, order_id: str | None = None) -> dict:
    params = params or {}
    rec: dict = {}
    cur = {k: int(v) for k, v in (contents.get("currencies") or {}).items() if int(v) > 0}
    if cur:
        rec["currencies"] = wallet_grant(db, user_id, cur, reason, ref)
    for code, n in (contents.get("shards") or {}).items():
        _add_shards(db, user_id, code, int(n), rec)
    if contents.get("shards_choice"):
        code = params.get("hero_code")
        if not code or db.get(Hero, code) is None or db.get(Hero, code).is_enemy:
            raise ValueError("hero_code required for shards_choice")
        _add_shards(db, user_id, code, int(contents["shards_choice"]), rec)
    for code in contents.get("heroes") or []:
        _add_hero(db, user_id, code, rec)
    if contents.get("hero_choice"):
        code = params.get("hero_code")
        h = db.get(Hero, code) if code else None
        if h is None or h.is_enemy or not h.summonable or h.rarity > int(contents["hero_choice"]["rarity_max"]):
            raise ValueError("invalid hero choice")
        _add_hero(db, user_id, code, rec)
    for cid in contents.get("cosmetics") or []:
        if cosmetic(cid):
            _entitle(db, user_id, "cosmetic", cid, None, order_id, "purchase", rec)
            rec.setdefault("cosmetics", []).append(cid)
    ent = contents.get("entitlement")
    if ent and ent.get("kind") == "subscription":
        sub = cfg()["subscriptions"][ent["code"]]
        e = _entitle(db, user_id, "subscription", ent["code"], int(ent.get("days", sub["days"])), order_id, "purchase", rec)
        for cid in sub.get("cosmetics", []) + sub.get("effects", []):  # time-limited cosmetics follow the subscription
            ce = Entitlement(user_id=user_id, kind="cosmetic", code=cid, starts_at=e.starts_at, expires_at=e.expires_at,
                             order_id=order_id, source="subscription")
            db.add(ce)
            db.flush()
            rec.setdefault("entitlements", []).append(ce.id)
        on = (sub.get("on_purchase") or {}).get("currencies") or {}
        if on:
            got = wallet_grant(db, user_id, on, reason, ref)
            for k, v in got.items():
                rec.setdefault("currencies", {})[k] = rec.get("currencies", {}).get(k, 0) + v
    if contents.get("bp_premium"):
        row = battlepass.progress(db, user_id, lock=True)
        if not row.premium:
            row.premium = True
            rec["bp_premium"] = row.season
            _entitle(db, user_id, "bp_premium", str(row.season), None, order_id, "purchase", rec)
    db.flush()
    owned = len(db.scalars(select(PlayerHero.id).where(PlayerHero.user_id == user_id)).all())
    quest_event(db, user_id, "hero_collected", absolute=owned)
    return rec


def revoke(db: Session, user_id: str, rec: dict, reason: str, ref: str) -> dict:
    """Reverse a grant. Never drives balances negative: what cannot be taken back is recorded as debt."""
    debt: dict = {}
    for k, v in (rec.get("currencies") or {}).items():
        w = db.get(Wallet, (user_id, k), with_for_update=True)
        bal = w.balance if w else 0
        take = min(bal, int(v))
        if take:
            apply_delta(db, user_id, {k: -take}, reason, ref)
        if take < int(v):
            debt.setdefault("currencies", {})[k] = int(v) - take
    for code, n in (rec.get("shards") or {}).items():
        ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == user_id, PlayerHero.hero_code == code))
        if ph:
            take = min(ph.shards, int(n))
            ph.shards -= take
            if take < int(n):
                debt.setdefault("shards", {})[code] = int(n) - take
    p = db.get(PlayerProfile, user_id, with_for_update=True)
    bank = dict(p.hero_shards or {})
    for code, n in (rec.get("hero_bank") or {}).items():
        take = min(bank.get(code, 0), int(n))
        bank[code] = bank.get(code, 0) - take
    p.hero_shards = bank
    if rec.get("heroes"):
        debt["heroes"] = rec["heroes"]  # heroes are not deleted automatically: admin dispute decides
    now = utcnow()
    for eid in rec.get("entitlements") or []:
        e = db.get(Entitlement, eid)
        if e and e.revoked_at is None:
            e.revoked_at = now
    if rec.get("bp_premium") is not None:
        row = battlepass.progress(db, user_id, lock=True)
        if row.season == rec["bp_premium"]:
            row.premium = False
    db.flush()
    return debt
