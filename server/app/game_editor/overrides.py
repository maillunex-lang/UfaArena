"""Admin layer over the static game content (heroes, campaign regions and stages, map positions).

The static content lives in code (`app/game/data.py`) and is upserted on every start (`seed_static`). Admin edits are
stored separately in `server_settings["game_overrides"]` and re-applied after every seed, so neither a restart nor a
code update erases them. Every change keeps the previous version for rollback and is logged (admin_actions).

Shape: {"heroes": {code: {"custom": bool, "disabled": bool, "fields": {...}}},
        "regions": {code: {"custom": bool, "hidden": bool, "fields": {...}}},
        "nodes": {code: {"custom": bool, "hidden": bool, "fields": {...}}}}"""
from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AdminAction, CampaignNode, CampaignRegion, Hero, ServerSetting

KEY = "game_overrides"
HIST = "game_overrides_history"
EMPTY = {"heroes": {}, "regions": {}, "nodes": {}}
HERO_DEFAULTS = {"title": "", "lore": "", "is_enemy": False, "summonable": True, "role": "", "kit": None, "extra": {},
                 "skill": {}, "model": "knight"}


def get(db: Session) -> dict:
    row = db.get(ServerSetting, KEY)
    v = copy.deepcopy(row.value) if row and row.value else {}
    return {k: dict(v.get(k) or {}) for k in EMPTY}


def save(db: Session, data: dict, who: str, action: str, details: dict) -> None:
    """Stores a new version (the previous one goes to the history, last 50) and applies it to the live tables."""
    cur = get(db)
    hist = db.get(ServerSetting, HIST)
    if hist is None:
        hist = ServerSetting(key=HIST, value={"items": []})
        db.add(hist)
    hist.value = {"items": (list((hist.value or {}).get("items", [])) + [
        {"at": utcnow().isoformat(), "by": who, "action": action, "data": cur}])[-50:]}
    row = db.get(ServerSetting, KEY)
    if row is None:
        row = ServerSetting(key=KEY, value={})
        db.add(row)
    row.value = copy.deepcopy(data)
    db.add(AdminAction(admin=who, action=action, details=details))
    db.flush()
    apply(db)


def history(db: Session) -> list[dict]:
    hist = db.get(ServerSetting, HIST)
    return [{"at": h["at"], "by": h["by"], "action": h["action"]} for h in (hist.value or {}).get("items", [])] if hist else []


def rollback(db: Session, who: str) -> dict:
    hist = db.get(ServerSetting, HIST)
    items = list((hist.value or {}).get("items", [])) if hist else []
    if not items:
        raise ValueError("Нет предыдущей версии")
    prev = items.pop()
    hist.value = {"items": items}
    row = db.get(ServerSetting, KEY)
    row.value = prev["data"]
    db.add(AdminAction(admin=who, action="game_overrides_rollback", details={"to": prev["at"], "undid": prev["action"]}))
    db.flush()
    _restore_static(db)
    apply(db)
    return {"undid": prev["action"], "at": prev["at"]}


def _restore_static(db: Session) -> None:
    """Re-applies the code version of the touched items (a rollback removes an edit completely)."""
    from ..game import data as D
    for h in D.HEROES:
        db.merge(Hero(**{**HERO_DEFAULTS, **h}))
    for r in D.REGIONS:
        db.merge(CampaignRegion(**r))
    for n in D.NODES:
        db.merge(CampaignNode(**{"region_code": "r1_shikhany", "is_boss": False, **n}))
    db.flush()


def apply(db: Session) -> dict:
    """Applies the admin layer to the live tables (idempotent). Called after seeding and after every admin change."""
    o = get(db)
    n = {"heroes": 0, "regions": 0, "nodes": 0}
    for code, ov in o["heroes"].items():
        f = dict(ov.get("fields") or {})
        row = db.get(Hero, code)
        if row is None:
            if not ov.get("custom"):
                continue
            row = Hero(code=code, **{**HERO_DEFAULTS, **{k: v for k, v in f.items() if k != "code"}})
            db.add(row)
        else:
            for k, v in f.items():
                if k == "extra":
                    row.extra = {**(row.extra or {}), **(v or {})}
                elif hasattr(row, k) and k != "code":
                    setattr(row, k, v)
        extra = dict(row.extra or {})
        extra["disabled"] = bool(ov.get("disabled"))
        row.extra = extra
        if ov.get("disabled"):
            row.summonable = False
        n["heroes"] += 1
    db.flush()
    for kind, model, pk in (("regions", CampaignRegion, "code"), ("nodes", CampaignNode, "code")):
        for code, ov in o[kind].items():
            f = dict(ov.get("fields") or {})
            row = db.get(model, code)
            if row is None:
                if not ov.get("custom"):
                    continue
                if kind == "nodes":
                    f = {"is_boss": False, "rewards": {}, "first_clear_rewards": {}, "enemies": [], "map_pos": [0, 0], **f}
                row = model(**{pk: code, **{k: v for k, v in f.items() if k != pk and hasattr(model, k)}})
                db.add(row)
            else:
                for k, v in f.items():
                    if hasattr(row, k) and k != pk:
                        setattr(row, k, v)
            n[kind] += 1
        db.flush()
    return n


def hidden_nodes(db: Session) -> set[str]:
    return {c for c, ov in get(db)["nodes"].items() if ov.get("hidden")}


def hidden_regions(db: Session) -> set[str]:
    return {c for c, ov in get(db)["regions"].items() if ov.get("hidden")}


def disabled_heroes(db: Session) -> set[str]:
    return {c for c, ov in get(db)["heroes"].items() if ov.get("disabled")}
