"""Summon, AFK rewards, fortress, quests, mail. Server-authoritative economy."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.config import get_settings
from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..game import data as D
from ..models import (
    AfkClaim, FortressBuilding, Hero, PlayerHero, PlayerMail, PlayerProfile, PlayerQuest, Quest, SummonHistory,
    SummonPool,
)
from ..monetization import battlepass as BP
from ..monetization import vip as VIP
from ..monetization.config import cfg as MCFG
from ..services import (
    afk_preview, building_levels, grant, hero_view, quest_event, spend, team_bonuses, today_period, wallet_dict,
)

router = APIRouter(tags=["economy"])
_rng = secrets.SystemRandom()


# ------------------------------------------------------------------ summon
class SummonIn(BaseModel):
    pool: str = Field(default="standard", max_length=32)
    count: int = Field(default=1)


def _roll_rarity(rates: dict[str, float]) -> int:
    x, acc = _rng.random(), 0.0
    for r in sorted(rates, key=int):
        acc += rates[r]
        if x < acc:
            return int(r)
    return 1


@router.post("/summon")
def summon(body: SummonIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
           db: Session = Depends(get_db)):
    if body.count not in (1, 10):
        raise GameError("bad_count", "Можно призвать 1 или 10 героев")

    def do():
        pool = db.get(SummonPool, body.pool)
        if pool is None or not pool.active:
            raise GameError("not_found", "Пул призыва недоступен", 404)
        cost = {k: v * body.count for k, v in pool.cost.items()}
        if body.count == 10 and "crystals" in cost:
            cost["crystals"] = int(cost["crystals"] * 0.9)  # x10 discount
        spend(db, user.id, cost, "summon", pool.code)
        profile = db.get(PlayerProfile, user.id, with_for_update=True)
        by_rarity: dict[int, list[str]] = {}
        for h in db.scalars(select(Hero).where(Hero.summonable.is_(True), Hero.is_enemy.is_(False))):
            by_rarity.setdefault(h.rarity, []).append(h.code)
        first_ever = db.scalar(select(SummonHistory.id).where(SummonHistory.user_id == user.id).limit(1)) is None
        results = []
        for i in range(body.count):
            pity_hit = False
            if first_ever and i == 0:
                code = D.ONBOARDING_SUMMON_HERO  # onboarding guarantee (documented in GDD notes)
                rarity = db.get(Hero, code).rarity
            else:
                profile.summon_pity += 1
                rarity = _roll_rarity(pool.rates)
                if rarity < pool.pity_min_rarity and profile.summon_pity >= pool.pity_threshold:
                    rarity, pity_hit = pool.pity_min_rarity, True
                while rarity not in by_rarity:
                    rarity -= 1
                code = _rng.choice(by_rarity[rarity])
            if rarity >= pool.pity_min_rarity:
                profile.summon_pity = 0
            ph = db.scalar(select(PlayerHero).where(PlayerHero.user_id == user.id, PlayerHero.hero_code == code))
            dup = ph is not None
            if dup:
                ph.shards += D.DUP_SHARDS[rarity]
                while ph.shards >= D.SHARDS_PER_STAR and ph.stars < D.MAX_STARS:
                    ph.shards -= D.SHARDS_PER_STAR
                    ph.stars += 1
            else:
                ph = PlayerHero(user_id=user.id, hero_code=code)
                db.add(ph)
            db.flush()
            db.add(SummonHistory(user_id=user.id, pool_code=pool.code, hero_code=code, rarity=rarity,
                                 was_duplicate=dup, pity_triggered=pity_hit))
            results.append({"hero_code": code, "rarity": rarity, "duplicate": dup, "pity": pity_hit,
                            "player_hero_id": ph.id})
        db.flush()
        owned = len(db.scalars(select(PlayerHero.id).where(PlayerHero.user_id == user.id)).all())
        quest_event(db, user.id, "summon", body.count)
        BP.add_xp(db, user.id, "summon", body.count)
        quest_event(db, user.id, "hero_collected", absolute=owned)
        audit(db, user.id, "summon", pool=pool.code, count=body.count, results=[r["hero_code"] for r in results])
        b = team_bonuses(db, user.id)
        heroes = {r["player_hero_id"]: hero_view(db.get(PlayerHero, r["player_hero_id"]), b) for r in results}
        return {"results": results, "heroes": heroes, "pity": profile.summon_pity,
                "pity_threshold": pool.pity_threshold, "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, "summon", body.model_dump(), do)


@router.get("/summon/pools")
def pools(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    return {"pity": p.summon_pity, "pools": [
        {"code": sp.code, "name": sp.name, "rates": sp.rates, "cost": sp.cost, "pity_threshold": sp.pity_threshold,
         "pity_min_rarity": sp.pity_min_rarity} for sp in db.scalars(select(SummonPool).where(SummonPool.active))]}


# ------------------------------------------------------------------ AFK
@router.get("/rewards/afk")
def afk_status(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return afk_preview(db, db.get(PlayerProfile, user.id))


@router.post("/rewards/afk/claim")
def afk_claim(user: CurrentUser = Depends(player), key: str = Depends(require_key), db: Session = Depends(get_db)):
    def do():
        profile = db.get(PlayerProfile, user.id, with_for_update=True)
        now = utcnow()
        prev = afk_preview(db, profile, now)
        if prev["elapsed_s"] < get_settings().afk_min_claim_interval_s:
            raise GameError("afk_too_soon", "Награды ещё копятся", 409)
        rewards = grant(db, user.id, prev["rewards"], "afk_claim")
        db.add(AfkClaim(user_id=user.id, period_start=as_utc(profile.afk_last_claim_at), period_end=now,
                        seconds_credited=prev["credited_s"], rewards=rewards))
        profile.afk_last_claim_at = now
        quest_event(db, user.id, "afk_claim")
        BP.add_xp(db, user.id, "afk_claim")
        from ..social import progression as SP
        SP.on(db, user.id, "afk_claim")
        VIP.daily_activity(db, user.id)
        return {"rewards": rewards, "credited_s": prev["credited_s"], "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, "afk_claim", {}, do)


# ------------------------------------------------------------------ fortress
def _fortress_view(db: Session, user_id: str) -> dict:
    lv = building_levels(db, user_id)
    out = []
    for code, cfg in D.BUILDINGS.items():
        level = lv.get(code, 1)
        maxed = level >= cfg["max_level"]
        out.append({"code": code, "name": cfg["name"], "level": level, "max_level": cfg["max_level"],
                    "effect": cfg["effect"], "locked": cfg.get("locked", False),
                    "upgrade_cost": None if maxed or cfg.get("locked") else D.building_upgrade_cost(code, level)})
    return {"buildings": out}


@router.get("/fortress")
def fortress(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return _fortress_view(db, user.id)


@router.post("/fortress/buildings/{code}/upgrade")
def fortress_upgrade(code: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                     db: Session = Depends(get_db)):
    def do():
        cfg = D.BUILDINGS.get(code)
        if cfg is None:
            raise GameError("not_found", "Здание не найдено", 404)
        if cfg.get("locked"):
            raise GameError("building_locked", "Здание пока недоступно")
        b = db.get(FortressBuilding, (user.id, code), with_for_update=True)
        if b is None:
            b = FortressBuilding(user_id=user.id, code=code, level=1)
            db.add(b)
        if b.level >= cfg["max_level"]:
            raise GameError("max_level", "Максимальный уровень")
        spend(db, user.id, D.building_upgrade_cost(code, b.level), "building_upgrade", code)
        b.level += 1
        db.flush()
        quest_event(db, user.id, "building_upgrade")
        audit(db, user.id, "fortress.upgrade", building=code, level=b.level)
        return {**_fortress_view(db, user.id), "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, f"fortress_upgrade:{code}", {}, do)


# ------------------------------------------------------------------ quests
def _quest_list(db: Session, user_id: str) -> list[dict]:
    period = today_period()
    rows = {pq.quest_code: pq for pq in db.scalars(select(PlayerQuest).where(PlayerQuest.user_id == user_id))}
    out = []
    for q in db.scalars(select(Quest).order_by(Quest.order)):
        pq = rows.get(q.code)
        progress, claimed = (pq.progress, pq.claimed_at is not None) if pq else (0, False)
        if q.kind == "daily" and pq and pq.period != period:
            progress, claimed = 0, False
        if q.requires:
            req = rows.get(q.requires)
            if req is None or req.claimed_at is None:
                continue  # chain step not yet available
        out.append({"code": q.code, "kind": q.kind, "title": q.title, "description": q.description,
                    "progress": progress, "target": q.target, "rewards": q.rewards, "claimed": claimed,
                    "claimable": (not claimed) and progress >= q.target})
    return out


@router.get("/quests")
def quests(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return {"quests": _quest_list(db, user.id)}


@router.post("/quests/{code}/claim")
def quest_claim(code: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                db: Session = Depends(get_db)):
    def do():
        q = db.get(Quest, code)
        if q is None:
            raise GameError("not_found", "Задание не найдено", 404)
        avail = {x["code"]: x for x in _quest_list(db, user.id)}
        if code not in avail:
            raise GameError("quest_locked", "Задание ещё не открыто", 403)
        pq = db.get(PlayerQuest, (user.id, code), with_for_update=True)
        if pq is None or not avail[code]["claimable"]:
            raise GameError("quest_not_ready", "Задание не выполнено или уже получено", 409)
        pq.claimed_at = utcnow()
        rewards = grant(db, user.id, q.rewards, "quest_reward", code)
        BP.add_xp(db, user.id, "quest_claim")
        from ..social import progression as SP
        SP.on(db, user.id, "quest_claim", ref=code)
        if q.kind in ("main", "side"):  # achievements give VIP XP (free VIP path)
            VIP.add_xp(db, user.id, MCFG()["vip"]["achievement_xp"], "achievement", code)
        return {"rewards": rewards, "wallet": wallet_dict(db, user.id), "quests": _quest_list(db, user.id)}

    return run_idempotent(db, user.id, key, f"quest_claim:{code}:{today_period()}", {}, do)


# ------------------------------------------------------------------ mail
def _mail_list(db: Session, user_id: str) -> list[dict]:
    now = utcnow()
    out = []
    for pm in db.scalars(select(PlayerMail).where(PlayerMail.user_id == user_id).order_by(PlayerMail.created_at.desc())):
        if pm.expires_at and as_utc(pm.expires_at) < now:
            continue
        m = pm.message
        out.append({"id": pm.id, "title": m.title, "body": m.body, "sender": m.sender, "attachments": m.attachments,
                    "claimed": pm.claimed_at is not None, "created_at": as_utc(pm.created_at).isoformat()})
    return out


@router.get("/mail")
def mail(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return {"mail": _mail_list(db, user.id)}


@router.post("/mail/{mail_id}/claim")
def mail_claim(mail_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
               db: Session = Depends(get_db)):
    def do():
        pm = db.get(PlayerMail, mail_id, with_for_update=True)
        if pm is None or pm.user_id != user.id:
            raise GameError("not_found", "Письмо не найдено", 404)
        if pm.claimed_at is not None:
            raise GameError("already_claimed", "Вложения уже получены", 409)
        if pm.expires_at and as_utc(pm.expires_at) < utcnow():
            raise GameError("mail_expired", "Срок письма истёк", 410)
        pm.claimed_at = pm.read_at = utcnow()
        rewards = grant(db, user.id, pm.message.attachments, "mail_claim", pm.id)
        return {"rewards": rewards, "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, f"mail_claim:{mail_id}", {}, do)
