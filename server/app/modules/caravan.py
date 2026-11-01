"""Caravan — the player's moving base (lore stage S4, docs/lore/URALIA_DEVELOPMENT_ROADMAP.md).

Modules are the former fortress buildings (same codes and levels, same upgrade endpoint) plus three new ones.
The council has no single captain: each member's influence is hidden and derived from story decisions, upgrades of
the modules they oversee and journeys; the most influential member gives a small bonus. The route follows the Roads
of Breath between the seven lands; a journey takes real time; a land gives its local bonus to the patrol (AFK).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..game import data as D
from ..models import CampaignNode, CampaignRegion, PlayerCampaignProgress, PlayerCaravan, PlayerStoryFlag

router = APIRouter(prefix="/caravan", tags=["caravan"])
START = "r1_shikhany"


# ------------------------------------------------------------------ state
def caravan_row(db: Session, user_id: str, lock: bool = False) -> PlayerCaravan:
    """The caravan of a player; a finished journey is settled (arrival) on access."""
    row = db.get(PlayerCaravan, user_id, with_for_update=lock)
    if row is None:
        row = PlayerCaravan(user_id=user_id, location=START, trips=0)
        db.add(row)
        db.flush()
    if row.destination and row.arrive_at and as_utc(row.arrive_at) <= utcnow():
        row.location, row.destination, row.depart_at, row.arrive_at = row.destination, None, None, None
        row.trips = (row.trips or 0) + 1
        db.flush()
    return row


def neighbours(code: str) -> list[str]:
    return [b if a == code else a for a, b in D.ROADS if code in (a, b)]


def opened_regions(db: Session, user_id: str) -> set[str]:
    """A land is open once its first stage is unlocked (the previous stage of the campaign is cleared)."""
    from ..services import ordered_nodes
    cleared = set(db.scalars(select(PlayerCampaignProgress.node_code).where(PlayerCampaignProgress.user_id == user_id)))
    out, prev_ok = set(), True
    for n in ordered_nodes(db):
        if prev_ok:
            out.add(n.region_code)
        prev_ok = n.code in cleared
    return out


# ------------------------------------------------------------------ council
def council_influence(db: Session, user_id: str) -> dict[str, int]:
    from ..services import building_levels
    inf = {k: 0 for k in D.COUNCIL}
    for f in db.scalars(select(PlayerStoryFlag).where(PlayerStoryFlag.user_id == user_id)):
        for member, delta in D.COUNCIL_FLAG_INFLUENCE.get(f.flag, {}).get(f.value, {}).items():
            inf[member] += delta
    lv = building_levels(db, user_id)
    for code, b in D.BUILDINGS.items():
        if b.get("overseer") in inf:
            inf[b["overseer"]] += max(0, lv.get(code, 1) - 1)
    row = db.get(PlayerCaravan, user_id)
    if row is not None:
        inf["zarkhan"] += (row.trips or 0) // 2
    return inf


def council_leader(db: Session, user_id: str) -> str | None:
    """The single most influential member; a tie at the top means a divided council (no leader bonus)."""
    inf = council_influence(db, user_id)
    top = max(inf.values())
    leaders = [k for k, v in inf.items() if v == top]
    return leaders[0] if top > 0 and len(leaders) == 1 else None


def leader_bonus(db: Session, user_id: str) -> tuple[str, float]:
    lead = council_leader(db, user_id)
    if not lead:
        return "", 0.0
    c = D.COUNCIL[lead]
    return c["lead_bonus"], float(c["lead_value"])


LINES = {
    "azamat": {"lead": "Караван под моей защитой. Пока я стою — люди спят спокойно.",
               "support": "Стражи на местах. Укрепи башни — и я буду спокоен.",
               "neutral": "Я присматриваюсь, хранитель. Защита каравана — не игра.",
               "doubt": "Ты рискуешь людьми. Я это запомню."},
    "gauhar": {"lead": "Повозки полны, торговля идёт! Со мной караван не будет голодать, жаным.",
               "support": "Торговые повозки — сердце каравана. Не забывай о них.",
               "neutral": "Посмотрим, хранитель, умеешь ли ты считать монеты.",
               "doubt": "Ты тратишь, не думая. Так караван разорится."},
    "ilsur": {"lead": "Механизмы печатей начинают отвечать. Мы близко к пониманию.",
              "support": "Библиотека и исследования важнее, чем кажется. Поверь мне.",
              "neutral": "Я наблюдаю. И слушаю — не только тебя.",
              "doubt": "Ты слишком охотно слушаешь голос в осколке. Это пугает."},
    "gulnaz": {"lead": "Лазарет справляется. Я рада, что ты принимаешь всех, кому нужна помощь.",
               "support": "Раненых много. Лазарету нужны травы и руки.",
               "neutral": "Я лечу всех. Даже тех, кого ты приводишь.",
               "doubt": "Людям нужна забота, а не только дорога."},
    "yurek": {"lead": "Разведка впереди каравана. Ни одна засада нас не застанет врасплох.",
              "support": "Хорошее оружие — половина охоты. Кузница ждёт заказов.",
              "neutral": "Я иду впереди и вижу дорогу. А ты?",
              "doubt": "Мы слишком долго стоим на месте. Лес не ждёт."},
    "zarkhan": {"lead": "Я знаю каждую дорогу Дыхания. Доверься мне — дойдём быстрее.",
                "support": "Дорога — лучший учитель. Чем больше пути, тем меньше бед.",
                "neutral": "Пути опаснее, чем кажутся. Не забывай об этом.",
                "doubt": "Караван, который никуда не едет, — лёгкая добыча."},
}


def council_view(db: Session, user_id: str) -> list[dict]:
    inf = council_influence(db, user_id)
    lead = council_leader(db, user_id)
    out = []
    for code, c in D.COUNCIL.items():
        v = inf[code]
        mood = "lead" if code == lead else ("support" if v >= 1 else ("neutral" if v == 0 else "doubt"))
        out.append({"code": code, "name": c["name"], "area": c["area"], "hero": c["hero"], "mood": mood,
                    "mood_text": {"lead": "Ближайший советник", "support": "Поддерживает вас", "neutral": "Присматривается",
                                  "doubt": "Сомневается в вас"}[mood],
                    "line": LINES[code][mood], "lead_text": c["lead_text"],
                    "modules": [k for k, b in D.BUILDINGS.items() if b.get("overseer") == code]})
    return out  # influence numbers are never sent to the client (hidden system, C17)


# ------------------------------------------------------------------ route
def land_bonus(db: Session, user_id: str) -> tuple[str, float]:
    row = db.get(PlayerCaravan, user_id)
    loc = START if row is None else (None if row.destination and row.arrive_at and as_utc(row.arrive_at) > utcnow() else
                                     (row.destination if row.destination else row.location))
    if loc is None:
        return "", 0.0
    cur, val, _ = D.LAND_BONUS.get(loc, ("", 0.0, ""))
    return cur, val


def travel_hours(db: Session, user_id: str) -> float:
    kind, val = leader_bonus(db, user_id)
    return D.ROAD_HOURS * (1 - val if kind == "travel" else 1)


def _region_names(db: Session) -> dict[str, str]:
    return {r.code: r.name for r in db.scalars(select(CampaignRegion))}


def caravan_view(db: Session, user_id: str) -> dict:
    from .economy import _fortress_view
    row = caravan_row(db, user_id)
    names = _region_names(db)
    opened = opened_regions(db, user_id)
    traveling = bool(row.destination)
    roads = []
    if not traveling:
        for code in neighbours(row.location):
            roads.append({"to": code, "name": names.get(code, code), "open": code in opened,
                          "hours": round(travel_hours(db, user_id), 2),
                          "bonus": D.LAND_BONUS.get(code, ("", 0, ""))[2],
                          "reason": "" if code in opened else "Откроется после прохождения предыдущей главы похода"})
    lead = council_leader(db, user_id)
    return {
        "location": row.location, "location_name": names.get(row.location, row.location),
        "location_bonus": "" if traveling else D.LAND_BONUS.get(row.location, ("", 0, ""))[2],
        "traveling": traveling, "destination": row.destination, "destination_name": names.get(row.destination or "", ""),
        "depart_at": as_utc(row.depart_at).isoformat() if row.depart_at else None,
        "arrive_at": as_utc(row.arrive_at).isoformat() if row.arrive_at else None,
        "trips": row.trips or 0, "roads": roads, "all_roads": D.ROADS, "opened": sorted(opened),
        "council": council_view(db, user_id), "leader": lead,
        "leader_text": D.COUNCIL[lead]["lead_text"] if lead else "Совет разделён — ни у кого нет перевеса",
        "modules": _fortress_view(db, user_id)["buildings"],
    }


@router.get("")
def caravan(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    out = caravan_view(db, user.id)
    db.commit()  # persists creation / arrival
    return out


class TravelIn(BaseModel):
    to: str = Field(max_length=32)


@router.post("/travel")
def travel(body: TravelIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
           db: Session = Depends(get_db)):
    def do():
        row = caravan_row(db, user.id, lock=True)
        if row.destination:
            raise GameError("traveling", "Караван уже в пути", 409)
        if body.to not in neighbours(row.location):
            raise GameError("no_road", "Туда нет прямой дороги", 400)
        if body.to not in opened_regions(db, user.id):
            raise GameError("land_locked", "Эта земля ещё не открыта в походе", 403)
        now = utcnow()
        row.destination, row.depart_at = body.to, now
        row.arrive_at = now + timedelta(hours=travel_hours(db, user.id))
        db.flush()
        from ..core.audit import audit
        audit(db, user.id, "caravan.travel", None, frm=row.location, to=body.to)
        return caravan_view(db, user.id)
    return run_idempotent(db, user.id, key, "caravan_travel", body.model_dump(), do)
