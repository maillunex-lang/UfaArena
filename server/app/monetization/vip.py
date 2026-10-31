"""VIP: 7 permanent levels. XP from purchases, daily activity and achievements (free path exists).
Perks are convenience/cosmetic + a capped AFK bonus; nothing applies to PvP."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import DailyActivity, PlayerProfile, VipRewardClaim, VipXpLog
from .config import cfg


def level_for(xp: int) -> int:
    lv = 0
    for i, need in enumerate(cfg()["vip"]["levels"]):
        if xp >= need:
            lv = i
    return min(lv, 7)


def add_xp(db: Session, user_id: str, delta: int, source: str, ref: str | None = None) -> int:
    if delta == 0:
        return db.get(PlayerProfile, user_id).vip_level
    p = db.get(PlayerProfile, user_id, with_for_update=True)
    p.vip_xp = max(0, (p.vip_xp or 0) + delta)
    p.vip_level = level_for(p.vip_xp)  # permanent: never decreases except on refunds
    db.add(VipXpLog(user_id=user_id, delta=delta, source=source, ref=ref))
    db.flush()
    return p.vip_level


def daily_activity(db: Session, user_id: str) -> bool:
    """First activity of the UTC day: VIP XP + battle pass daily XP. Returns True if it was new."""
    day = utcnow().strftime("%Y-%m-%d")
    if db.get(DailyActivity, (user_id, day)) is not None:
        return False
    db.add(DailyActivity(user_id=user_id, day=day))
    db.flush()
    add_xp(db, user_id, cfg()["vip"]["daily_activity_xp"], "daily", day)
    from . import battlepass
    battlepass.add_xp(db, user_id, "daily_login")
    return True


def afk_bonus(level: int) -> float:
    v = cfg()["vip"]
    return min(v["afk_bonus_cap"], v["afk_bonus_per_level"] * level)


def battle_speeds(level: int) -> list[int]:
    out = [1, 2]
    for k, sp in cfg()["vip"]["battle_speeds"].items():
        if level >= int(k):
            out = sp
    return out


def view(db: Session, user_id: str) -> dict:
    p = db.get(PlayerProfile, user_id)
    lv, xp = p.vip_level or 0, p.vip_xp or 0
    levels = cfg()["vip"]["levels"]
    claimed = set(db.scalars(select(VipRewardClaim.level).where(VipRewardClaim.user_id == user_id)))
    hist = db.scalars(select(VipXpLog).where(VipXpLog.user_id == user_id).order_by(VipXpLog.id.desc()).limit(20)).all()
    return {
        "level": lv, "xp": xp, "next_xp": levels[lv + 1] if lv < 7 else None, "levels": levels,
        "afk_bonus": afk_bonus(lv), "battle_speeds": battle_speeds(lv),
        "perks": cfg()["vip"]["perks"], "rewards": cfg()["vip"]["rewards"],
        "claimable": [n for n in range(1, lv + 1) if n not in claimed], "claimed": sorted(claimed),
        "history": [{"delta": h.delta, "source": h.source, "ref": h.ref, "at": h.created_at.isoformat()} for h in hist],
        "sources": {"purchase_per_rub": cfg()["vip"]["xp_per_rub"], "daily": cfg()["vip"]["daily_activity_xp"],
                    "achievement": cfg()["vip"]["achievement_xp"]},
    }
