"""Admin game editor API (/admin/api/game/*): heroes (create, edit, disable, balance report), campaign (regions and
stages), map positions. Same admin authentication; every change goes through the override layer (history, rollback)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.errors import GameError
from ..models import Faction, Hero, HeroClass, PlayerHero
from ..modules.admin import admin
from . import balance as BAL
from . import overrides as OV

router = APIRouter(prefix="/admin/api/game", tags=["game-editor"])

RIGS = ["knight", "barbarian", "mage", "rogue", "rogue_hooded", "skeleton_minion", "skeleton_warrior", "skeleton_rogue",
        "skeleton_mage", "dragon", "tree"]
SKILL_KINDS = {"strike": "Удар", "aoe": "Удар по площади", "heal": "Лечение", "shield": "Щит", "stun": "Оглушение"}
HERO_FIELDS = ("name", "title", "faction_code", "class_code", "rarity", "base_hp", "base_atk", "base_def", "base_spd",
               "skill", "model", "lore", "is_enemy", "summonable", "role", "kit", "extra")
LIMITS = {"rarity": (1, 6), "base_hp": (50, 200000), "base_atk": (1, 20000), "base_def": (0, 20000), "base_spd": (10, 400)}


def _hero_view(db: Session, h: Hero, ov: dict) -> dict:
    owners = db.scalar(select(func.count()).select_from(PlayerHero).where(PlayerHero.hero_code == h.code)) or 0
    o = ov.get(h.code) or {}
    return {"code": h.code, "name": h.name, "title": h.title, "faction_code": h.faction_code, "class_code": h.class_code,
            "rarity": h.rarity, "base_hp": h.base_hp, "base_atk": h.base_atk, "base_def": h.base_def, "base_spd": h.base_spd,
            "skill": h.skill, "model": h.model, "lore": h.lore, "is_enemy": h.is_enemy, "summonable": h.summonable,
            "role": h.role, "kit": h.kit, "extra": h.extra or {}, "owners": owners, "custom": bool(o.get("custom")),
            "edited": bool(o.get("fields")) and not o.get("custom"), "disabled": bool(o.get("disabled"))}


def _validate(db: Session, f: dict) -> dict:
    out = {}
    for k, v in f.items():
        if k not in HERO_FIELDS:
            raise GameError("bad_field", f"Неизвестное поле: {k}", 400)
        if k in LIMITS:
            lo, hi = LIMITS[k]
            if not isinstance(v, int) or not lo <= v <= hi:
                raise GameError("bad_value", f"{k}: целое число {lo}…{hi}", 400)
        if k == "faction_code" and db.get(Faction, v) is None:
            raise GameError("bad_faction", "Неизвестная фракция", 400)
        if k == "class_code" and db.get(HeroClass, v) is None:
            raise GameError("bad_class", "Неизвестный класс", 400)
        if k in ("name", "title", "role", "model") and (not isinstance(v, str) or len(v) > (64 if k != "title" else 128)):
            raise GameError("bad_value", f"{k}: строка", 400)
        if k == "name" and not v.strip():
            raise GameError("bad_value", "Имя не может быть пустым", 400)
        if k == "lore" and (not isinstance(v, str) or len(v) > 4000):
            raise GameError("bad_value", "Описание до 4000 символов", 400)
        if k == "skill":
            if not isinstance(v, dict) or v.get("kind") not in (*SKILL_KINDS, "kit"):
                raise GameError("bad_skill", "Умение: kind из " + ", ".join(SKILL_KINDS), 400)
            if not 0 <= float(v.get("power", 1)) <= 10:
                raise GameError("bad_skill", "Сила умения 0…10", 400)
        if k == "kit" and v is not None:
            if not isinstance(v, dict) or not isinstance(v.get("basic"), dict):
                raise GameError("bad_kit", "Набор умений: объект с полем basic (см. образец)", 400)
            for part in [v.get("basic"), v.get("ultimate"), *(v.get("skills") or [])]:
                for e in (part or {}).get("effects", []) if isinstance(part, dict) else []:
                    if e.get("type") == "damage" and not 0 < float(e.get("mult", 1)) * int(e.get("hits", 1)) <= 15:
                        raise GameError("bad_kit", "Урон одного умения: множитель × удары от 0 до 15", 400)
        if k == "extra":
            if not isinstance(v, dict):
                raise GameError("bad_value", "extra: объект", 400)
            g = v.get("growth") or {}
            if any(not 0 <= float(x) <= 0.3 for x in g.values()):
                raise GameError("bad_value", "Рост за уровень: 0…0.3", 400)
            if not 0 <= float(v.get("crit", 0.12)) <= 0.9 or not 1 <= float(v.get("crit_dmg", 1.5)) <= 5:
                raise GameError("bad_value", "Крит 0…0.9, урон крита 1…5", 400)
        out[k] = v
    return out


@router.get("/meta")
def meta(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"factions": [{"code": f.code, "name": f.name} for f in db.scalars(select(Faction))],
            "classes": [{"code": c.code, "name": c.name, "role": c.role} for c in db.scalars(select(HeroClass))],
            "rigs": RIGS, "skill_kinds": SKILL_KINDS,
            "kit_sample": {"basic": {"name": "Удар", "desc": "", "effects": [{"type": "damage", "target": "target", "mult": 1.0, "hits": 1}]},
                           "skills": [], "ultimate": {"name": "Ульта", "desc": "", "effects": [{"type": "damage", "target": "target", "mult": 2.0}]},
                           "passive": None, "mechanic": None}}


@router.get("/heroes")
def heroes(enemies: bool = Query(False), who: str = Depends(admin), db: Session = Depends(get_db)):
    ov = OV.get(db)["heroes"]
    q = select(Hero).order_by(Hero.is_enemy, Hero.rarity.desc(), Hero.name)
    if not enemies:
        q = q.where(Hero.is_enemy.is_(False))
    return {"items": [_hero_view(db, h, ov) for h in db.scalars(q)]}


class HeroIn(BaseModel):
    code: str | None = Field(None, max_length=48)
    fields: dict


@router.post("/heroes")
def create_hero(body: HeroIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    code = (body.code or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", code):
        raise GameError("bad_code", "Код героя: латиница в нижнем регистре, цифры, «_», 3–41 символ", 400)
    if db.get(Hero, code) is not None:
        raise GameError("exists", "Герой с таким кодом уже есть", 409)
    f = _validate(db, body.fields)
    for need in ("name", "faction_code", "class_code", "rarity", "base_hp", "base_atk", "base_def", "base_spd"):
        if need not in f:
            raise GameError("missing", f"Не заполнено: {need}", 400)
    f.setdefault("skill", {"kind": "strike", "name": "Удар", "power": 1.5, "desc": ""})
    data = OV.get(db)
    data["heroes"][code] = {"custom": True, "disabled": False, "fields": f}
    OV.save(db, data, who, "hero_create", {"code": code, "name": f["name"]})
    db.commit()
    return _hero_view(db, db.get(Hero, code), OV.get(db)["heroes"])


@router.put("/heroes/{code}")
def edit_hero(code: str, body: HeroIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    h = db.get(Hero, code)
    if h is None:
        raise GameError("not_found", "Герой не найден", 404)
    f = _validate(db, body.fields)
    data = OV.get(db)
    cur = data["heroes"].get(code) or {"custom": False, "disabled": False, "fields": {}}
    cur["fields"] = {**cur.get("fields", {}), **f}
    data["heroes"][code] = cur
    OV.save(db, data, who, "hero_edit", {"code": code, "fields": sorted(f)})
    db.commit()
    return _hero_view(db, db.get(Hero, code), OV.get(db)["heroes"])


class DisableIn(BaseModel):
    disabled: bool


@router.post("/heroes/{code}/disable")
def disable_hero(code: str, body: DisableIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """A disabled hero leaves summoning and the catalog; players who own it keep it and can still use it."""
    h = db.get(Hero, code)
    if h is None:
        raise GameError("not_found", "Герой не найден", 404)
    data = OV.get(db)
    cur = data["heroes"].get(code) or {"custom": False, "fields": {}}
    cur["disabled"] = body.disabled
    if not body.disabled:
        from ..game import data as D
        static = next((x for x in D.HEROES if x["code"] == code), None)
        cur.setdefault("fields", {})["summonable"] = bool((cur.get("fields") or {}).get("summonable",
                                                         static.get("summonable", True) if static else True))
    data["heroes"][code] = cur
    OV.save(db, data, who, "hero_disable" if body.disabled else "hero_enable", {"code": code})
    db.commit()
    return _hero_view(db, db.get(Hero, code), OV.get(db)["heroes"])


@router.delete("/heroes/{code}/override")
def reset_hero(code: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Back to the code version (edits removed). A custom hero is removed only if nobody owns it."""
    data = OV.get(db)
    cur = data["heroes"].get(code)
    if cur is None:
        raise GameError("not_found", "У героя нет правок", 404)
    if cur.get("custom"):
        if db.scalar(select(func.count()).select_from(PlayerHero).where(PlayerHero.hero_code == code)):
            raise GameError("owned", "Героя уже получили игроки — его можно только отключить", 409)
        data["heroes"].pop(code)
        OV.save(db, data, who, "hero_delete", {"code": code})
        h = db.get(Hero, code)
        if h is not None:
            db.delete(h)
    else:
        data["heroes"].pop(code)
        OV.save(db, data, who, "hero_reset", {"code": code})
        OV._restore_static(db)
        OV.apply(db)
    db.commit()
    return {"ok": True}


@router.get("/balance")
def balance(level: int = Query(40, ge=1, le=200), stars: int = Query(0, ge=0, le=10), duels: bool = Query(False),
            who: str = Depends(admin), db: Session = Depends(get_db)):
    return BAL.report(db, level, stars, duels)


@router.get("/history")
def history(who: str = Depends(admin), db: Session = Depends(get_db)):
    return {"items": list(reversed(OV.history(db)))[:50]}


@router.post("/rollback")
def rollback(who: str = Depends(admin), db: Session = Depends(get_db)):
    try:
        r = OV.rollback(db, who)
    except ValueError as e:
        raise GameError("no_history", str(e), 409)
    db.commit()
    return r
