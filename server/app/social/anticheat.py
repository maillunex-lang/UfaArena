"""Anti-cheat signals. Results are already server-authoritative (the client never sends damage, wins,
rewards or ratings); this module looks for anomalies — bot-like request timing, improbable outcomes,
ledger mismatches, abnormal income — and files flags for moderator review. It never bans by itself."""
from __future__ import annotations

import statistics
import time
from collections import deque
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_engine, utcnow
from ..models import Order, PlayerProfile, SuspicionFlag, WalletTransaction
from ..services import ledger_consistent

_times: dict[str, deque] = {}
_flagged_at: dict[tuple[str, str], float] = {}


def flag(db: Session, user_id: str, kind: str, score: int = 1, **details) -> bool:
    """One open flag per (user, kind) per hour; duplicates only raise the score."""
    now = time.monotonic()
    if now - _flagged_at.get((user_id, kind), -1e9) < 3600:
        return False
    _flagged_at[(user_id, kind)] = now
    open_flag = db.scalar(select(SuspicionFlag).where(SuspicionFlag.user_id == user_id, SuspicionFlag.kind == kind,
                                                      SuspicionFlag.status == "open"))
    if open_flag:
        open_flag.score += score
        open_flag.details = {**(open_flag.details or {}), "last": details}
    else:
        db.add(SuspicionFlag(user_id=user_id, kind=kind, score=score, details=details))
    db.flush()
    return True


def observe(user_id: str) -> None:
    """Called on every authenticated request: near-constant intervals over a long run look automated."""
    now = time.monotonic()
    q = _times.setdefault(user_id, deque(maxlen=40))
    q.append(now)
    if len(q) < 40:
        return
    gaps = [b - a for a, b in zip(q, list(q)[1:])]
    mean = statistics.mean(gaps)
    if mean < 4.0 and statistics.pstdev(gaps) < 0.03:
        try:
            with Session(get_engine()) as db:
                if flag(db, user_id, "bot_timing", 1, mean_gap=round(mean, 3), stdev=round(statistics.pstdev(gaps), 4)):
                    db.commit()
        except Exception:
            pass
        q.clear()


def check_pvp(db: Session, user_id: str, att: list[dict], dfn: list[dict], won: bool) -> None:
    pa = sum(int(u.get("power", 0)) for u in att)
    pd = sum(int(u.get("power", 0)) for u in dfn)
    if won and pd > 0 and pa < pd * 0.45:
        flag(db, user_id, "improbable_win", 1, attacker_power=pa, defender_power=pd)


def economy_scan(db: Session, limit: int = 200) -> dict:
    """Ledger integrity on recently active players + abnormal 24h crystal income without paid orders."""
    since = utcnow() - timedelta(hours=24)
    active = list(db.scalars(select(PlayerProfile.user_id).where(PlayerProfile.is_ai.is_(False))
                             .order_by(PlayerProfile.last_seen_at.desc().nullslast()).limit(limit)))
    mismatches = 0
    for uid in active:
        if not ledger_consistent(db, uid):
            mismatches += 1
            flag(db, uid, "ledger_mismatch", 5)
    rich = db.execute(select(WalletTransaction.user_id, func.sum(WalletTransaction.delta)).where(
        WalletTransaction.currency == "crystals", WalletTransaction.delta > 0, WalletTransaction.created_at >= since,
        WalletTransaction.reason.notin_(("purchase", "order_fulfill", "subscription_daily", "starting_wallet")))
        .group_by(WalletTransaction.user_id).having(func.sum(WalletTransaction.delta) > 20000)).all()
    for uid, total in rich:
        paid = db.scalar(select(func.count()).select_from(Order).where(Order.user_id == uid, Order.created_at >= since)) or 0
        if not paid:
            flag(db, uid, "abnormal_income", 2, crystals_24h=int(total))
    db.flush()
    return {"checked": len(active), "ledger_mismatches": mismatches, "abnormal_income": len(rich)}


