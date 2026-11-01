"""PvP arena 5v5: Elo rating, leagues, 30-day seasons with a partial reset and rewards, defense squads,
defense history and deterministic replays. Ranked matches are between real players only; AI personas
play in a separate training ladder and never change real players' ratings."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import ArenaMatch, ArenaProfile, ArenaSeason, PlayerProfile, SeasonResult
from ..services import wallet_dict
from . import progression as P
from .common import card, cfg, day, freeze_squad, give, league_of, notify, pvp, squad_power, summary

router = APIRouter(prefix="/arena", tags=["arena"])


def A() -> dict:
    return cfg()["arena"]


# ------------------------------------------------------------------ seasons
def current_season(db: Session) -> ArenaSeason:
    s = db.scalar(select(ArenaSeason).where(ArenaSeason.status == "active").order_by(ArenaSeason.id.desc()))
    if s is not None and as_utc(s.ends_at) <= utcnow():
        close_season(db, s)
        s = None
    if s is None:
        last = db.scalar(select(func.max(ArenaSeason.id))) or 0
        now = utcnow()
        s = ArenaSeason(id=last + 1, starts_at=now, ends_at=now + timedelta(days=A()["season_days"]), status="active")
        db.add(s)
        db.flush()
    return s


def close_season(db: Session, s: ArenaSeason) -> dict:
    """Rewards by league, permanent history rows, partial rating reset. Idempotent per season."""
    if s.status != "active":
        return s.summary or {}
    rows = db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(False)).order_by(ArenaProfile.rating.desc())).all()
    start, keep = A()["start_rating"], A()["reset_keep"]
    rewarded = 0
    for rank_no, ap in enumerate(rows, start=1):
        lg = league_of(ap.rating)
        conf = next(x for x in A()["leagues"] if x["code"] == lg["code"])
        if ap.wins + ap.losses > 0:
            notify(db, ap.user_id, f"Сезон арены {s.id} завершён",
                   f"Итог: {ap.rating} очков, лига «{lg['name']}», место {rank_no}.", conf["reward"])
            rewarded += 1
        if not db.scalar(select(SeasonResult).where(SeasonResult.user_id == ap.user_id, SeasonResult.category == "arena",
                                                    SeasonResult.season_id == s.id)):
            db.add(SeasonResult(user_id=ap.user_id, category="arena", season_id=s.id, ref=f"arena:{s.id}",
                                result={"rating": ap.rating, "league": lg["name"], "rank": rank_no, "wins": ap.wins,
                                        "losses": ap.losses}))
        ap.rating = int(start + (ap.rating - start) * keep)
        ap.wins = ap.losses = ap.def_wins = ap.def_losses = 0
        ap.season_id = s.id + 1
    for ap in db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(True))):
        ap.rating = int(start + (ap.rating - start) * keep)
        ap.wins = ap.losses = 0
    s.status = "closed"
    s.summary = {"players": len(rows), "rewarded": rewarded, "top": [card(db, r.user_id)["nickname"] for r in rows[:3]]}
    db.flush()
    return s.summary


# ------------------------------------------------------------------ profiles
def ensure_profile(db: Session, user_id: str, lock: bool = False) -> ArenaProfile:
    ap = db.get(ArenaProfile, user_id, with_for_update=lock)
    if ap is None:
        p = db.get(PlayerProfile, user_id)
        try:
            spec = freeze_squad(db, user_id)
        except GameError:
            spec = []
        ap = ArenaProfile(user_id=user_id, rating=A()["start_rating"], best_rating=A()["start_rating"], defense=spec,
                          defense_power=squad_power(spec), is_ai=bool(p and p.is_ai), day=day(),
                          season_id=current_season(db).id)
        db.add(ap)
        db.flush()
    if ap.day != day():
        ap.day, ap.attempts_used, ap.training_used = day(), 0, 0
    return ap


def elo(ra: int, rb: int, score: float) -> int:
    exp = 1 / (1 + 10 ** ((rb - ra) / 400))
    return round(A()["k"] * (score - exp))


def candidates(db: Session, me: ArenaProfile) -> dict:
    """Transparent matchmaking: closest rating inside the window, then closest defense power. No hidden factors."""
    w = A()["rating_window"]
    rows = db.scalars(select(ArenaProfile).where(
        ArenaProfile.is_ai.is_(False), ArenaProfile.user_id != me.user_id, ArenaProfile.defense_power > 0,
        ArenaProfile.rating.between(me.rating - w, me.rating + w)).limit(200)).all()
    rows.sort(key=lambda r: (abs(r.rating - me.rating) // 25, abs(r.defense_power - me.defense_power)))
    ranked = [_opp(db, r, me.user_id) for r in rows[: A()["candidates"]]]
    ai = db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(True), ArenaProfile.defense_power > 0)
                    .order_by(func.abs(ArenaProfile.defense_power - me.defense_power)).limit(3)).all()
    return {"ranked": ranked, "training": [_opp(db, r, me.user_id) for r in ai]}


def _opp(db: Session, ap: ArenaProfile, viewer: str) -> dict:
    c = card(db, ap.user_id, viewer)
    return {"user_id": ap.user_id, "nickname": c["nickname"], "level": c["level"], "is_ai": c["is_ai"],
            "rating": ap.rating, "league": league_of(ap.rating)["name"], "power": ap.defense_power,
            "guild": c["guild"], "defense": [{k: u[k] for k in ("hero_code", "level", "stars", "slot")} for u in ap.defense],
            "win_delta": elo(db.get(ArenaProfile, viewer).rating if db.get(ArenaProfile, viewer) else 1000, ap.rating, 1)}


def match_view(db: Session, m: ArenaMatch, viewer: str) -> dict:
    attacking = m.attacker_id == viewer
    other = m.defender_id if attacking else m.attacker_id
    won = (m.result == "victory") == attacking
    return {"id": m.id, "kind": m.kind, "role": "attack" if attacking else "defense", "won": won,
            "opponent": card(db, other)["nickname"], "opponent_is_ai": card(db, other)["is_ai"],
            "delta": m.delta_att if attacking else m.delta_def, "at": as_utc(m.created_at).isoformat()}


@router.get("")
def arena(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    s = current_season(db)
    ap = ensure_profile(db, user.id)
    hist = db.scalars(select(ArenaMatch).where(or_(ArenaMatch.attacker_id == user.id, ArenaMatch.defender_id == user.id))
                      .order_by(ArenaMatch.created_at.desc()).limit(15)).all()
    defenses = [m for m in hist if m.defender_id == user.id]
    rank_no = (db.scalar(select(func.count()).select_from(ArenaProfile).where(
        ArenaProfile.is_ai.is_(False), ArenaProfile.rating > ap.rating)) or 0) + 1
    out = {
        "season": {"id": s.id, "ends_at": as_utc(s.ends_at).isoformat(), "leagues": A()["leagues"]},
        "me": {"rating": ap.rating, "best": ap.best_rating, "league": league_of(ap.rating), "rank": None if ap.is_ai else rank_no,
               "wins": ap.wins, "losses": ap.losses, "def_wins": ap.def_wins, "def_losses": ap.def_losses,
               "attempts_left": max(0, A()["attempts_per_day"] - ap.attempts_used),
               "training_left": max(0, A()["training_per_day"] - ap.training_used),
               "defense": ap.defense, "defense_power": ap.defense_power},
        "candidates": candidates(db, ap), "history": [match_view(db, m, user.id) for m in hist],
        "defense_analysis": {"total": len(defenses), "won": sum(1 for m in defenses if m.result == "defeat"),
                             "note": "Защита считается выигранной, если атакующий проиграл"},
        "rewards": {"win": A()["win_reward"], "loss": A()["loss_reward"], "training": A()["training_reward"]},
    }
    db.commit()
    return out


class DefenseIn(BaseModel):
    slots: list[str | None] = Field(min_length=5, max_length=5)


@router.post("/defense")
def set_defense(body: DefenseIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    ap = ensure_profile(db, user.id, lock=True)
    spec = freeze_squad(db, user.id, body.slots)
    ap.defense, ap.defense_power, ap.updated_at = spec, squad_power(spec), utcnow()
    db.commit()
    return {"defense": spec, "defense_power": ap.defense_power}


class FightIn(BaseModel):
    opponent_id: str = Field(max_length=36)
    kind: str = Field(default="ranked", pattern="^(ranked|training)$")
    slots: list[str | None] | None = Field(default=None, min_length=5, max_length=5)


@router.post("/fight")
def fight(body: FightIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
          db: Session = Depends(get_db)):
    def do():
        s = current_season(db)
        me = ensure_profile(db, user.id, lock=True)
        if me.is_ai:
            raise GameError("forbidden", "Недоступно", 403)
        opp = db.get(ArenaProfile, body.opponent_id, with_for_update=True)
        if opp is None or opp.user_id == user.id or not opp.defense:
            raise GameError("not_found", "Соперник не найден", 404)
        if body.kind == "ranked":
            if opp.is_ai:
                raise GameError("ai_not_ranked", "ИИ-соперники доступны только в тренировочных боях", 400)
            if abs(opp.rating - me.rating) > A()["rating_window"] * 2:
                raise GameError("out_of_range", "Соперник вне вашего диапазона рейтинга", 400)
            if me.attempts_used >= A()["attempts_per_day"]:
                raise GameError("no_attempts", "Рейтинговые попытки на сегодня закончились", 409)
            me.attempts_used += 1
        else:
            if me.training_used >= A()["training_per_day"]:
                raise GameError("no_attempts", "Тренировочные бои на сегодня закончились", 409)
            me.training_used += 1
        att = freeze_squad(db, user.id, body.slots)
        seed = secrets.randbits(48)
        sim = pvp(db, att, opp.defense, seed)
        won = sim["result"] == "victory"
        d_att = d_def = 0
        if body.kind == "ranked":
            d_att = elo(me.rating, opp.rating, 1.0 if won else 0.0)
            d_def = -round(d_att * 0.5)
            me.rating = max(0, me.rating + d_att)
            opp.rating = max(0, opp.rating + d_def)
            me.best_rating = max(me.best_rating, me.rating)
            if won:
                me.wins += 1
                opp.def_losses += 1
            else:
                me.losses += 1
                opp.def_wins += 1
            reward = give(db, user.id, A()["win_reward"] if won else A()["loss_reward"], "arena", s.id and str(s.id))
            P.on(db, user.id, "arena_win" if won else "arena_loss")
        else:
            reward = give(db, user.id, A()["training_reward"], "arena_training")
        m = ArenaMatch(season_id=s.id, kind=body.kind, attacker_id=user.id, defender_id=opp.user_id,
                       result=sim["result"], delta_att=d_att, delta_def=d_def, seed=seed,
                       attacker_snapshot=att, defender_snapshot=opp.defense)
        db.add(m)
        db.flush()
        from .anticheat import check_pvp
        check_pvp(db, user.id, att, opp.defense, won)
        if opp.is_ai:  # the AI resident remembers who beat it (or lost to it): rivalry and respect (stage 16)
            from ..ai import social as SOC
            SOC.relate(db, opp.user_id, user.id, "arena_loss" if won else "arena_win")
        return {"simulation": sim, "match_id": m.id, "won": won, "delta": d_att, "rating": me.rating,
                "league": league_of(me.rating), "reward": reward, "wallet": wallet_dict(db, user.id),
                "summary": summary(sim)}
    return run_idempotent(db, user.id, key, f"arena_fight:{body.opponent_id}", body.model_dump(), do)


@router.get("/replay/{match_id}")
def replay(match_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Re-simulates the match from its seed and frozen squads (the engine is deterministic)."""
    m = db.get(ArenaMatch, match_id)
    if m is None:
        raise GameError("not_found", "Бой не найден", 404)
    sim = pvp(db, m.attacker_snapshot, m.defender_snapshot, m.seed)
    return {"simulation": sim, "match": match_view(db, m, user.id) if user.id in (m.attacker_id, m.defender_id) else None,
            "attacker": card(db, m.attacker_id)["nickname"], "defender": card(db, m.defender_id)["nickname"],
            "consistent": sim["result"] == m.result}
