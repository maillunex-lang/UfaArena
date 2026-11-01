"""Campaign editor (admin): chapters (regions) and stages — order, names, descriptions, terrain, enemies, rewards,
dialogues, map positions; hide/show; difficulty check with the real battle engine. Works through the override layer.

Player progress is never lost: a cleared stage stays cleared even when it is hidden or moved; a stage inserted before a
player's current position will be offered to them as the next one."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.errors import GameError
from ..models import CampaignNode, CampaignRegion, Hero, PlayerCampaignProgress
from ..modules.admin import admin
from . import overrides as OV

router = APIRouter(prefix="/admin/api/game/campaign", tags=["game-editor"])
TERRITORIES = {"nature": "Природа", "settlements": "Поселения", "dungeons": "Подземелья", "resources": "Рудники",
               "complexes": "Древние комплексы", "dimensions": "Иные измерения"}
CURRENCIES = ("gold", "crystals", "summon_essence", "nature_essence", "ancient_seals", "guild_marks", "friend_tokens", "raid_tickets")
SPEAKERS = ["narrator", "ilsur", "aisylu", "timer", "bayras", "kahym", "gauhar", "ancient"]


def _region_view(db: Session, r: CampaignRegion, ov: dict) -> dict:
    o = ov.get(r.code) or {}
    return {"code": r.code, "order": r.order, "name": r.name, "real_place": r.real_place, "description": r.description,
            "custom": bool(o.get("custom")), "hidden": bool(o.get("hidden")), "edited": bool(o.get("fields")) and not o.get("custom")}


def _node_view(db: Session, n: CampaignNode, ov: dict) -> dict:
    o = ov.get(n.code) or {}
    cleared = db.scalar(select(func.count()).select_from(PlayerCampaignProgress).where(PlayerCampaignProgress.node_code == n.code)) or 0
    return {"code": n.code, "region_code": n.region_code, "order": n.order, "name": n.name, "territory": n.territory,
            "real_place": n.real_place, "map_pos": n.map_pos, "is_boss": n.is_boss, "rewards": n.rewards,
            "first_clear_rewards": n.first_clear_rewards, "story": n.story, "enemies": n.enemies, "players_cleared": cleared,
            "custom": bool(o.get("custom")), "hidden": bool(o.get("hidden")), "edited": bool(o.get("fields")) and not o.get("custom")}


def _rewards(v, name: str) -> dict:
    if not isinstance(v, dict) or any(k not in CURRENCIES or not isinstance(a, int) or not 0 <= a <= 1_000_000 for k, a in v.items()):
        raise GameError("bad_rewards", f"{name}: ресурсы из списка, целые 0…1 000 000", 400)
    return v


def _validate_node(db: Session, f: dict) -> dict:
    out = {}
    for k, v in f.items():
        if k == "name":
            if not isinstance(v, str) or not v.strip() or len(v) > 128:
                raise GameError("bad_value", "Название этапа: 1–128 символов", 400)
        elif k == "region_code":
            if db.get(CampaignRegion, v) is None:
                raise GameError("bad_region", "Нет такой главы", 400)
        elif k == "order":
            if not isinstance(v, int) or not 1 <= v <= 1000:
                raise GameError("bad_value", "Порядок 1…1000", 400)
        elif k == "territory":
            if v not in TERRITORIES:
                raise GameError("bad_value", "Местность: " + ", ".join(TERRITORIES), 400)
        elif k == "real_place":
            if not isinstance(v, str) or len(v) > 255:
                raise GameError("bad_value", "Место: до 255 символов", 400)
        elif k == "is_boss":
            v = bool(v)
        elif k in ("rewards", "first_clear_rewards"):
            v = _rewards(v, "Награды" if k == "rewards" else "Награды за первое прохождение")
        elif k == "map_pos":
            if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and -100 <= x <= 100 for x in v)):
                raise GameError("bad_value", "Позиция на карте: [x, y] от -100 до 100", 400)
        elif k == "enemies":
            if not isinstance(v, list) or not 1 <= len(v) <= 5:
                raise GameError("bad_enemies", "Враги: от 1 до 5", 400)
            slots = set()
            for e in v:
                if db.get(Hero, e.get("hero_code", "")) is None:
                    raise GameError("bad_enemies", f"Нет героя/врага с кодом {e.get('hero_code')}", 400)
                if not isinstance(e.get("level"), int) or not 1 <= e["level"] <= 200:
                    raise GameError("bad_enemies", "Уровень врага 1…200", 400)
                if not isinstance(e.get("slot"), int) or not 0 <= e["slot"] <= 4 or e["slot"] in slots:
                    raise GameError("bad_enemies", "Позиции врагов 0…4, без повторов (0–1 — передний ряд)", 400)
                slots.add(e["slot"])
            v = [{"hero_code": e["hero_code"], "level": e["level"], "slot": e["slot"]} for e in v]
        elif k == "story":
            if not isinstance(v, list) or len(v) > 30 or any(not isinstance(x, dict) or not str(x.get("text", "")).strip()
                                                            or len(str(x.get("text"))) > 600 for x in v):
                raise GameError("bad_story", "Диалог: до 30 реплик по 600 символов", 400)
            v = [{"speaker": str(x.get("speaker") or "narrator")[:32], "text": str(x["text"])} for x in v]
        else:
            raise GameError("bad_field", f"Неизвестное поле: {k}", 400)
        out[k] = v
    return out


def _validate_region(f: dict) -> dict:
    out = {}
    for k, v in f.items():
        if k in ("name", "real_place", "description"):
            lim = {"name": 128, "real_place": 255, "description": 4000}[k]
            if not isinstance(v, str) or len(v) > lim or (k == "name" and not v.strip()):
                raise GameError("bad_value", f"{k}: строка до {lim}", 400)
        elif k == "order":
            if not isinstance(v, int) or not 1 <= v <= 1000:
                raise GameError("bad_value", "Порядок главы 1…1000", 400)
        else:
            raise GameError("bad_field", f"Неизвестное поле: {k}", 400)
        out[k] = v
    return out


@router.get("")
def campaign(who: str = Depends(admin), db: Session = Depends(get_db)):
    o = OV.get(db)
    regions = [_region_view(db, r, o["regions"]) for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order))]
    nodes = [_node_view(db, n, o["nodes"]) for n in db.scalars(select(CampaignNode).order_by(CampaignNode.order))]
    heroes = [{"code": h.code, "name": h.name, "rarity": h.rarity, "is_enemy": h.is_enemy}
              for h in db.scalars(select(Hero).order_by(Hero.is_enemy.desc(), Hero.rarity, Hero.name))]
    return {"regions": regions, "nodes": nodes, "heroes": heroes, "territories": TERRITORIES, "currencies": list(CURRENCIES),
            "speakers": SPEAKERS}


class ItemIn(BaseModel):
    code: str | None = Field(None, max_length=32)
    fields: dict


@router.post("/regions")
def create_region(body: ItemIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    code = (body.code or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", code) or db.get(CampaignRegion, code) is not None:
        raise GameError("bad_code", "Код главы: латиница/цифры/«_», 3–32 символа, уникальный", 400)
    f = _validate_region(body.fields)
    if "name" not in f or "order" not in f:
        raise GameError("missing", "Нужны название и порядок", 400)
    f.setdefault("real_place", "")
    f.setdefault("description", "")
    data = OV.get(db)
    data["regions"][code] = {"custom": True, "hidden": False, "fields": f}
    OV.save(db, data, who, "region_create", {"code": code})
    db.commit()
    return _region_view(db, db.get(CampaignRegion, code), OV.get(db)["regions"])


@router.put("/regions/{code}")
def edit_region(code: str, body: ItemIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if db.get(CampaignRegion, code) is None:
        raise GameError("not_found", "Глава не найдена", 404)
    f = _validate_region(body.fields)
    data = OV.get(db)
    cur = data["regions"].get(code) or {"custom": False, "hidden": False, "fields": {}}
    cur["fields"] = {**cur.get("fields", {}), **f}
    data["regions"][code] = cur
    OV.save(db, data, who, "region_edit", {"code": code, "fields": sorted(f)})
    db.commit()
    return _region_view(db, db.get(CampaignRegion, code), OV.get(db)["regions"])


class HideIn(BaseModel):
    hidden: bool


@router.post("/regions/{code}/hide")
def hide_region(code: str, body: HideIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if db.get(CampaignRegion, code) is None:
        raise GameError("not_found", "Глава не найдена", 404)
    data = OV.get(db)
    cur = data["regions"].get(code) or {"custom": False, "fields": {}}
    cur["hidden"] = body.hidden
    data["regions"][code] = cur
    OV.save(db, data, who, "region_hide" if body.hidden else "region_show", {"code": code})
    db.commit()
    return {"ok": True}


@router.post("/nodes")
def create_node(body: ItemIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    code = (body.code or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_\-]{1,31}", code) or db.get(CampaignNode, code) is not None:
        raise GameError("bad_code", "Код этапа: буквы/цифры/«-», «_», 2–32 символа, уникальный (например 8-1)", 400)
    f = _validate_node(db, body.fields)
    for need in ("region_code", "order", "name", "territory", "enemies"):
        if need not in f:
            raise GameError("missing", f"Не заполнено: {need}", 400)
    f.setdefault("rewards", {"gold": 200})
    f.setdefault("first_clear_rewards", {"crystals": 30})
    f.setdefault("story", [])
    f.setdefault("map_pos", [0, 0])
    f.setdefault("real_place", "")
    data = OV.get(db)
    data["nodes"][code] = {"custom": True, "hidden": False, "fields": f}
    OV.save(db, data, who, "node_create", {"code": code, "region": f["region_code"]})
    db.commit()
    return _node_view(db, db.get(CampaignNode, code), OV.get(db)["nodes"])


@router.put("/nodes/{code}")
def edit_node(code: str, body: ItemIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if db.get(CampaignNode, code) is None:
        raise GameError("not_found", "Этап не найден", 404)
    f = _validate_node(db, body.fields)
    data = OV.get(db)
    cur = data["nodes"].get(code) or {"custom": False, "hidden": False, "fields": {}}
    cur["fields"] = {**cur.get("fields", {}), **f}
    data["nodes"][code] = cur
    OV.save(db, data, who, "node_edit", {"code": code, "fields": sorted(f)})
    db.commit()
    return _node_view(db, db.get(CampaignNode, code), OV.get(db)["nodes"])


@router.post("/nodes/{code}/hide")
def hide_node(code: str, body: HideIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if db.get(CampaignNode, code) is None:
        raise GameError("not_found", "Этап не найден", 404)
    data = OV.get(db)
    cur = data["nodes"].get(code) or {"custom": False, "fields": {}}
    cur["hidden"] = body.hidden
    data["nodes"][code] = cur
    OV.save(db, data, who, "node_hide" if body.hidden else "node_show", {"code": code})
    db.commit()
    return {"ok": True}


@router.delete("/nodes/{code}/override")
def reset_node(code: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    data = OV.get(db)
    cur = data["nodes"].get(code)
    if cur is None:
        raise GameError("not_found", "У этапа нет правок", 404)
    if cur.get("custom"):
        if db.scalar(select(func.count()).select_from(PlayerCampaignProgress).where(PlayerCampaignProgress.node_code == code)):
            raise GameError("progress", "Этап уже проходили игроки — его можно только скрыть", 409)
        data["nodes"].pop(code)
        OV.save(db, data, who, "node_delete", {"code": code})
        n = db.get(CampaignNode, code)
        if n is not None:
            db.delete(n)
    else:
        data["nodes"].pop(code)
        OV.save(db, data, who, "node_reset", {"code": code})
        OV._restore_static(db)
        OV.apply(db)
    db.commit()
    return {"ok": True}


class ReorderIn(BaseModel):
    region_code: str = Field(max_length=32)
    codes: list[str] = Field(max_length=200)


@router.post("/nodes/reorder")
def reorder(body: ReorderIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Sets the play order of a chapter's stages (1…n) in the given sequence."""
    rows = [db.get(CampaignNode, c) for c in body.codes]
    if any(r is None or r.region_code != body.region_code for r in rows):
        raise GameError("bad_order", "Все этапы должны быть из этой главы", 400)
    data = OV.get(db)
    for i, c in enumerate(body.codes, start=1):
        cur = data["nodes"].get(c) or {"custom": False, "hidden": False, "fields": {}}
        cur["fields"] = {**cur.get("fields", {}), "order": i}
        data["nodes"][c] = cur
    OV.save(db, data, who, "nodes_reorder", {"region": body.region_code, "codes": body.codes})
    db.commit()
    return {"ok": True}


@router.get("/nodes/{code}/simulate")
def simulate_node(code: str, level: int = Query(10, ge=1, le=200), stars: int = Query(0, ge=0, le=10), runs: int = Query(5, ge=1, le=20),
                  who: str = Depends(admin), db: Session = Depends(get_db)):
    """Difficulty check: the five strongest playable heroes at the given level fight this stage with the real engine."""
    from ..game import roster as R
    from ..game.battle_sim import hero_stats, make_unit, power_rating, simulate
    from ..modules.game import _enemy_units
    from ..services import hero_dict
    n = db.get(CampaignNode, code)
    if n is None:
        raise GameError("not_found", "Этап не найден", 404)
    adv = R.advantage()
    pool = [hero_dict(h) for h in db.scalars(select(Hero).where(Hero.is_enemy.is_(False), Hero.summonable.is_(True)))]
    pool.sort(key=lambda hd: -power_rating(hero_stats(hd, level, stars)))
    tanks = [hd for hd in pool if hd["class_code"] in ("guardian", "warrior")][:2]
    team = (tanks + [hd for hd in pool if hd not in tanks])[:5]
    wins, rounds = 0, []
    for _ in range(runs):
        units = [make_unit(0, i, hd, hero_stats(hd, level, stars), level, adv.get(hd["faction_code"])) for i, hd in enumerate(team)]
        res = simulate(units, _enemy_units(db, n), secrets.randbits(40))
        wins += res["result"] == "victory"
        rounds.append(res["rounds"])
    enemy_power = sum(power_rating(hero_stats(hero_dict(db.get(Hero, e["hero_code"])), e["level"])) for e in n.enemies)
    team_power = sum(power_rating(hero_stats(hd, level, stars)) for hd in team)
    return {"level": level, "team": [hd["name"] for hd in team], "win_pct": round(100 * wins / runs), "avg_rounds": round(sum(rounds) / runs, 1),
            "team_power": team_power, "enemy_power": enemy_power}


# ------------------------------------------------------------------ map editor
@router.get("/map")
def map_data(who: str = Depends(admin), db: Session = Depends(get_db)):
    """Everything the visual map editor needs: chapters with stage positions (hex coordinates of the region map) and
    chapter positions on the world map (fractions 0…1)."""
    o = OV.get(db)
    world = {**OV.WORLD_DEFAULT, **(o.get("world_map") or {})}
    regions = []
    for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order)):
        nodes = [{"code": n.code, "name": n.name, "order": n.order, "map_pos": n.map_pos or [0, 0], "is_boss": n.is_boss,
                  "hidden": bool((o["nodes"].get(n.code) or {}).get("hidden"))}
                 for n in sorted(db.scalars(select(CampaignNode).where(CampaignNode.region_code == r.code)), key=lambda x: x.order)]
        regions.append({"code": r.code, "name": r.name, "order": r.order, "world": world.get(r.code),
                        "hidden": bool((o["regions"].get(r.code) or {}).get("hidden")), "nodes": nodes})
    from ..admin_web import art
    return {"regions": regions, "world_map_art": "ui/world_map.png" in art.index()["files"],
            "roads": [list(x) for x in __import__("app.game.data", fromlist=["ROADS"]).ROADS]}


class NodePositionsIn(BaseModel):
    positions: dict[str, list[int]]


@router.put("/map/nodes")
def save_node_positions(body: NodePositionsIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Stage checkpoints on the region map (hex coordinates, integers — read by the current app too)."""
    data = OV.get(db)
    for code, pos in body.positions.items():
        if db.get(CampaignNode, code) is None:
            raise GameError("not_found", f"Нет этапа {code}", 404)
        if len(pos) != 2 or any(not -60 <= int(x) <= 60 for x in pos):
            raise GameError("bad_value", "Координаты точки -60…60", 400)
        cur = data["nodes"].get(code) or {"custom": False, "hidden": False, "fields": {}}
        cur["fields"] = {**cur.get("fields", {}), "map_pos": [int(pos[0]), int(pos[1])]}
        data["nodes"][code] = cur
    OV.save(db, data, who, "map_nodes", {"count": len(body.positions)})
    db.commit()
    return {"ok": True}


class WorldPositionsIn(BaseModel):
    positions: dict[str, list[float]]


@router.put("/map/world")
def save_world_positions(body: WorldPositionsIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    data = OV.get(db)
    wm = dict(data.get("world_map") or {})
    for code, xy in body.positions.items():
        if db.get(CampaignRegion, code) is None:
            raise GameError("not_found", f"Нет главы {code}", 404)
        if len(xy) != 2 or any(not 0 <= float(x) <= 1 for x in xy):
            raise GameError("bad_value", "Позиция на карте мира: доли 0…1", 400)
        wm[code] = [round(float(xy[0]), 4), round(float(xy[1]), 4)]
    data["world_map"] = wm
    OV.save(db, data, who, "map_world", {"count": len(body.positions)})
    db.commit()
    return {"ok": True}
