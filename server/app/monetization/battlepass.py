"""Battle pass: 30-day seasons, free + premium tracks, XP from regular play.
Buying premium mid-season unlocks premium rewards for all levels already reached."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import BattlePassProgress
from .config import cfg


def _epoch() -> datetime:
    return datetime.fromisoformat(cfg()["battlepass"]["epoch"].replace("Z", "+00:00"))


def season_index(now: datetime | None = None) -> int:
    now = now or utcnow()
    return max(0, int((now - _epoch()).total_seconds() // (cfg()["battlepass"]["season_days"] * 86400)))


def season_bounds(idx: int) -> tuple[datetime, datetime]:
    d = cfg()["battlepass"]["season_days"]
    start = _epoch() + timedelta(days=d * idx)
    return start, start + timedelta(days=d)


def progress(db: Session, user_id: str, lock: bool = False) -> BattlePassProgress:
    s = season_index()
    row = db.get(BattlePassProgress, (user_id, s), with_for_update=lock)
    if row is None:
        row = BattlePassProgress(user_id=user_id, season=s, xp=0, premium=False, claimed_free=[], claimed_premium=[])
        db.add(row)
        db.flush()
    return row


def level_of(xp: int) -> int:
    bp = cfg()["battlepass"]
    return min(len(bp["levels"]), xp // bp["xp_per_level"])


def add_xp(db: Session, user_id: str, source: str, times: int = 1) -> None:
    amount = cfg()["battlepass"]["xp"].get(source, 0) * times
    if amount <= 0:
        return
    row = progress(db, user_id, lock=True)
    cap = len(cfg()["battlepass"]["levels"]) * cfg()["battlepass"]["xp_per_level"]
    row.xp = min(cap, row.xp + amount)
    db.flush()


def view(db: Session, user_id: str) -> dict:
    row = progress(db, user_id)
    bp = cfg()["battlepass"]
    s = row.season
    start, end = season_bounds(s)
    names = bp["season_names"]
    return {"season": s, "name": names[s % len(names)], "starts": start.isoformat(), "ends": end.isoformat(),
            "xp": row.xp, "level": level_of(row.xp), "xp_per_level": bp["xp_per_level"], "premium": row.premium,
            "claimed_free": row.claimed_free, "claimed_premium": row.claimed_premium, "levels": bp["levels"],
            "xp_sources": bp["xp"]}
