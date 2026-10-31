"""Domain services shared by API modules. All functions run inside the caller's
DB transaction; the router commits once at the end so side effects are atomic."""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.db import as_utc, utcnow
from .core.errors import GameError
from .game import data as D
from .game import roster as R
from .game.battle_sim import hero_stats, power_rating
from .models import (
    CURRENCIES,
    CampaignNode,
    FortressBuilding,
    Formation,
    Hero,
    MailMessage,
    PlayerCampaignProgress,
    PlayerHero,
    PlayerMail,
    PlayerProfile,
    PlayerQuest,
    Quest,
    User,
    Wallet,
    WalletTransaction,
)


# ------------------------------------------------------------------ wallet / ledger
def _wallet_row(db: Session, user_id: str, currency: str) -> Wallet:
    if currency not in CURRENCIES:
        raise GameError("bad_currency", f"Неизвестная валюта {currency}")
    w = db.get(Wallet, (user_id, currency), with_for_update=True)
    if w is None:
        w = Wallet(user_id=user_id, currency=currency, balance=0)
        db.add(w)
        db.flush()
    return w


def apply_delta(db: Session, user_id: str, deltas: dict[str, int], reason: str, ref: str | None = None) -> None:
    """Atomically apply currency changes. Debits are checked before any write."""
    rows = {c: _wallet_row(db, user_id, c) for c in sorted(deltas)}
    for c, d in deltas.items():
        if rows[c].balance + d < 0:
            raise GameError("insufficient_funds", f"Недостаточно ресурса: {c}", 409)
    for c, d in deltas.items():
        if d == 0:
            continue
        w = rows[c]
        w.balance += d
        db.add(WalletTransaction(user_id=user_id, currency=c, delta=d, balance_after=w.balance, reason=reason, ref=ref))
    db.flush()


def grant(db: Session, user_id: str, rewards: dict[str, int], reason: str, ref: str | None = None) -> dict:
    rewards = {k: int(v) for k, v in rewards.items() if int(v) > 0}
    if rewards:
        apply_delta(db, user_id, rewards, reason, ref)
    return rewards


def spend(db: Session, user_id: str, cost: dict[str, int], reason: str, ref: str | None = None) -> None:
    apply_delta(db, user_id, {k: -int(v) for k, v in cost.items()}, reason, ref)


def wallet_dict(db: Session, user_id: str) -> dict[str, int]:
    out = {c: 0 for c in CURRENCIES}
    for w in db.scalars(select(Wallet).where(Wallet.user_id == user_id)):
        out[w.currency] = w.balance
    return out


def ledger_consistent(db: Session, user_id: str) -> bool:
    """Wallet reconciliation: cached balance == sum of ledger."""
    sums = dict(
        db.execute(
            select(WalletTransaction.currency, func.sum(WalletTransaction.delta))
            .where(WalletTransaction.user_id == user_id)
            .group_by(WalletTransaction.currency)
        ).all()
    )
    return all(int(sums.get(c, 0)) == b for c, b in wallet_dict(db, user_id).items())


# ------------------------------------------------------------------ quests
def today_period() -> str:
    return utcnow().strftime("%Y-%m-%d")


def quest_event(db: Session, user_id: str, event: str, amount: int = 1, absolute: int | None = None) -> None:
    for q in db.scalars(select(Quest).where(Quest.event == event)):
        period = today_period() if q.kind == "daily" else "once"
        pq = db.get(PlayerQuest, (user_id, q.code))
        if pq is None:
            pq = PlayerQuest(user_id=user_id, quest_code=q.code, progress=0, period=period)
            db.add(pq)
        elif q.kind == "daily" and pq.period != period:
            pq.period, pq.progress, pq.claimed_at = period, 0, None
        if pq.claimed_at is not None:
            continue
        pq.progress = min(q.target, absolute if absolute is not None else pq.progress + amount)
    db.flush()


# ------------------------------------------------------------------ fortress bonuses
def building_levels(db: Session, user_id: str) -> dict[str, int]:
    return {b.code: b.level for b in db.scalars(select(FortressBuilding).where(FortressBuilding.user_id == user_id))}


def team_bonuses(db: Session, user_id: str) -> dict:
    lv = building_levels(db, user_id)
    return {"atk_pct": 0.03 * (lv.get("forge", 1) - 1), "hp_pct": 0.03 * (lv.get("training", 1) - 1)}


def hero_view(ph: PlayerHero, bonuses: dict | None = None) -> dict:
    h = ph.hero
    st = hero_stats(_hero_dict(h), ph.level, ph.stars, **(bonuses or {}))
    return {
        "id": ph.id, "hero_code": h.code, "name": h.name, "title": h.title, "faction": h.faction_code,
        "class": h.class_code, "rarity": h.rarity, "rarity_name": D.RARITIES[h.rarity], "model": h.model,
        "level": ph.level, "stars": ph.stars, "shards": ph.shards, "stats": st, "power": power_rating(st),
        "skill": h.skill, "level_up_cost": D.level_up_cost(ph.level) if ph.level < D.LEVEL_CAP_MVP else None,
        "role": h.role or "", "role_name": (h.extra or {}).get("role_name", ""),
        "crit": (h.extra or {}).get("crit", 0.12), "crit_dmg": (h.extra or {}).get("crit_dmg", 1.5),
        "kit": h.kit or R.legacy_kit(h.skill or {}, h.class_code, h.rarity),
        "skill_level": 1 + ph.stars,
    }


def _hero_dict(h: Hero) -> dict:
    return {
        "code": h.code, "name": h.name, "rarity": h.rarity, "base_hp": h.base_hp, "base_atk": h.base_atk,
        "base_def": h.base_def, "base_spd": h.base_spd, "faction_code": h.faction_code,
        "class_code": h.class_code, "model": h.model, "skill": h.skill, "kit": h.kit, "extra": h.extra or {},
    }


hero_dict = _hero_dict


# ------------------------------------------------------------------ AFK
def cleared_count(db: Session, user_id: str) -> int:
    return db.scalar(select(func.count()).select_from(PlayerCampaignProgress).where(PlayerCampaignProgress.user_id == user_id)) or 0


def afk_rates(db: Session, user_id: str) -> dict:
    """Per-hour AFK production, derived from server-side progress only."""
    cleared = cleared_count(db, user_id)
    lv = building_levels(db, user_id)
    from .monetization.vip import afk_bonus
    prof = db.get(PlayerProfile, user_id)
    vb = 1 + afk_bonus(prof.vip_level or 0) if prof else 1.0  # capped VIP bonus (PvE only)
    out = {
        "gold": 600 + 200 * cleared,
        "nature_essence": round((20 + 6 * cleared) * (1 + 0.10 * (lv.get("alchemy", 1) - 1)), 2),
        "summon_essence": round(lv.get("summon_hall", 1) / 8.0, 4),
        "crystals": 5 + 2 * cleared,
    }
    out["gold"] = int(out["gold"] * vb)
    out["nature_essence"] = round(out["nature_essence"] * vb, 2)
    return out


def afk_cap_hours(db: Session, user_id: str) -> int:
    return get_settings().afk_max_hours_base + (building_levels(db, user_id).get("storage", 1) - 1)


def afk_preview(db: Session, profile: PlayerProfile, now: datetime | None = None) -> dict:
    now = now or utcnow()
    last = as_utc(profile.afk_last_claim_at)
    elapsed = max(0, int((now - last).total_seconds()))
    cap_s = afk_cap_hours(db, profile.user_id) * 3600
    credited = min(elapsed, cap_s)
    rates = afk_rates(db, profile.user_id)
    rewards = {k: int(v * credited / 3600) for k, v in rates.items()}
    return {"elapsed_s": elapsed, "credited_s": credited, "cap_s": cap_s, "rates_per_hour": rates,
            "rewards": rewards, "since": last.isoformat()}


# ------------------------------------------------------------------ player creation
def _uralia_id(db: Session) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        cand = "UR-" + "".join(secrets.choice(alphabet) for _ in range(8))
        if db.scalar(select(PlayerProfile).where(PlayerProfile.uralia_id == cand)) is None:
            return cand


def create_player(db: Session, device_id: str | None) -> User:
    user = User(kind="guest", device_id=device_id)
    db.add(user)
    db.flush()
    db.add(PlayerProfile(user_id=user.id, uralia_id=_uralia_id(db),
                         nickname=f"Хранитель-{secrets.randbelow(9000) + 1000}", afk_last_claim_at=utcnow()))
    db.flush()
    grant(db, user.id, D.STARTING_WALLET, "starting_wallet")
    slots: list[str | None] = []
    for code in D.STARTER_HEROES:
        ph = PlayerHero(user_id=user.id, hero_code=code, level=1)
        db.add(ph)
        db.flush()
        slots.append(ph.id)
    # azamat (tank) in front, the rest behind; 5 slots total
    db.add(Formation(user_id=user.id, kind="campaign", slots=(slots + [None] * 5)[:5]))
    for code in D.BUILDINGS:
        db.add(FortressBuilding(user_id=user.id, code=code, level=1))
    msg = db.scalar(select(MailMessage).where(MailMessage.code == D.WELCOME_MAIL["code"]))
    if msg is not None:
        db.add(PlayerMail(user_id=user.id, message_id=msg.id, expires_at=utcnow() + timedelta(days=30)))
    db.flush()
    quest_event(db, user.id, "hero_collected", absolute=len(D.STARTER_HEROES))
    return user


def ordered_nodes(db: Session) -> list[CampaignNode]:
    """All stages in play order: chapter (region order), then stage order."""
    from .models import CampaignRegion
    rorder = {r.code: r.order for r in db.scalars(select(CampaignRegion))}
    return sorted(db.scalars(select(CampaignNode)), key=lambda n: (rorder.get(n.region_code, 99), n.order))


def next_node(db: Session, user_id: str) -> CampaignNode | None:
    cleared = set(db.scalars(select(PlayerCampaignProgress.node_code).where(PlayerCampaignProgress.user_id == user_id)))
    for n in ordered_nodes(db):
        if n.code not in cleared:
            return n
    return None


def node_unlocked(db: Session, user_id: str, node: CampaignNode) -> bool:
    """A stage opens when the previous stage in play order is cleared (also across chapters)."""
    nodes = ordered_nodes(db)
    i = next(k for k, n in enumerate(nodes) if n.code == node.code)
    return i == 0 or db.get(PlayerCampaignProgress, (user_id, nodes[i - 1].code)) is not None

