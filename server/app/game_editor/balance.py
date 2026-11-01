"""Balance report for the hero roster: stats at a level, the strongest single hit against an average defender
(one-shot detection), power outliers within a rarity and an optional 1-vs-1 round robin with the real battle engine."""
from __future__ import annotations

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..game import roster as R
from ..game.battle_sim import hero_stats, make_unit, power_rating, simulate
from ..models import Hero
from ..services import hero_dict


def _max_mult(hd: dict) -> tuple[float, str]:
    """The biggest damage multiplier of one action (all hits of one skill), and its name."""
    kit = hd.get("kit") or R.legacy_kit(hd.get("skill") or {}, hd["class_code"], hd["rarity"])
    best, name = 1.0, "базовая атака"
    for key in ("basic", "ultimate"):
        part = kit.get(key) or {}
        tot = sum(float(e.get("mult", 0)) * int(e.get("hits", 1)) for e in part.get("effects", []) if e.get("type") == "damage")
        if tot > best:
            best, name = tot, part.get("name", key)
    for part in kit.get("skills") or []:
        tot = sum(float(e.get("mult", 0)) * int(e.get("hits", 1)) for e in part.get("effects", []) if e.get("type") == "damage")
        if tot > best:
            best, name = tot, part.get("name", "умение")
    return best, name


def report(db: Session, level: int = 40, stars: int = 0, duels: bool = False) -> dict:
    from .overrides import disabled_heroes
    off = disabled_heroes(db)
    rows = [h for h in db.scalars(select(Hero).where(Hero.is_enemy.is_(False)).order_by(Hero.rarity, Hero.code)) if h.code not in off]
    data = []
    for h in rows:
        hd = hero_dict(h)
        st = hero_stats(hd, level, stars)
        mult, skill = _max_mult(hd)
        crit_dmg = float((hd.get("extra") or {}).get("crit_dmg", 1.5))
        data.append({"code": h.code, "name": h.name, "rarity": h.rarity, "class": h.class_code, "faction": h.faction_code,
                     "summonable": h.summonable, "hp": st["hp"], "atk": st["atk"], "def": st["def"], "spd": st["spd"],
                     "power": power_rating(st), "max_mult": round(mult, 2), "max_skill": skill, "crit_dmg": crit_dmg, "hd": hd})
    if not data:
        return {"level": level, "heroes": [], "notes": ["Нет героев"]}
    med_hp = statistics.median(d["hp"] for d in data)
    med_def = statistics.median(d["def"] for d in data)
    by_rarity: dict[int, list[int]] = {}
    for d in data:
        by_rarity.setdefault(d["rarity"], []).append(d["power"])
    for d in data:
        a = d["atk"]
        hit = a * d["max_mult"] * (a / (a + med_def * 0.8))
        d["max_hit"] = int(hit * 1.1)                      # top of the ±10% variance
        d["max_crit_hit"] = int(hit * 1.1 * d["crit_dmg"])
        d["hit_pct_of_hp"] = round(100 * d["max_crit_hit"] / max(1, med_hp), 1)
        grp = by_rarity[d["rarity"]]
        mean = statistics.mean(grp)
        sd = statistics.pstdev(grp) or 1
        d["power_z"] = round((d["power"] - mean) / sd, 2) if len(grp) > 2 else 0.0
        flags = []
        if d["max_crit_hit"] >= med_hp:
            flags.append("убивает среднего героя с одного удара (крит)")
        elif d["max_hit"] >= 0.6 * med_hp:
            flags.append("снимает больше 60% здоровья одним ударом")
        if d["power_z"] >= 2:
            flags.append("заметно сильнее героев своей редкости")
        if d["power_z"] <= -2:
            flags.append("заметно слабее героев своей редкости")
        d["flags"] = flags
    if duels:
        wins = {d["code"]: 0 for d in data}
        games = {d["code"]: 0 for d in data}
        adv = R.advantage()
        for i, a in enumerate(data):
            for b in data[i + 1:]:
                for seed in (11, 23):
                    ua = make_unit(0, 0, a["hd"], hero_stats(a["hd"], level, stars), level, adv.get(a["faction"]))
                    ub = make_unit(1, 0, b["hd"], hero_stats(b["hd"], level, stars), level, adv.get(b["faction"]))
                    res = simulate([ua], [ub], seed)["result"]
                    games[a["code"]] += 1
                    games[b["code"]] += 1
                    wins[a["code"] if res == "victory" else b["code"]] += 1
        for d in data:
            d["duel_win_pct"] = round(100 * wins[d["code"]] / max(1, games[d["code"]]), 1)
            if d["duel_win_pct"] >= 85 and len(data) > 4:
                d["flags"].append(f"выигрывает {d['duel_win_pct']}% дуэлей один на один")
    for d in data:
        d.pop("hd", None)
    return {"level": level, "stars": stars, "median_hp": int(med_hp), "median_def": int(med_def), "heroes": data,
            "flagged": [d["code"] for d in data if d["flags"]]}
