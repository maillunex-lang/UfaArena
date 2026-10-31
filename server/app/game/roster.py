"""Data-driven roster: factions, classes, heroes (kits), summons and battle tunables.

Source of truth: app/game/content/roster.json (built from docs/design/URALIA_HERO_FORGE_12_Heroes.md).
New heroes/factions are added there without touching the battle engine. Legacy heroes from the
first vertical slice (data.HEROES) are adapted to the same kit format, so the engine has one path.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONTENT = Path(__file__).parent / "content" / "roster.json"

RARITY_MULT = {1: 1.0, 2: 1.12, 3: 1.25, 4: 1.42, 5: 1.62, 6: 1.85}


@lru_cache
def roster() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


def battle_cfg() -> dict:
    return roster()["battle"]


def factions() -> list[dict]:
    return roster()["factions"]


def faction_rules() -> dict:
    return roster()["faction_rules"]


def classes() -> list[dict]:
    return roster()["classes"]


def class_range(cls: str) -> float:
    for c in classes():
        if c["code"] == cls:
            return float(c["range"])
    return 1.8


def summons() -> dict:
    return roster()["summons"]


def map_faction(code: str) -> str:
    """Legacy provisional factions (slice 0.1) -> official factions."""
    return faction_rules()["legacy_map"].get(code, code)


def advantage() -> dict[str, str | None]:
    out = {f["code"]: f.get("strong_against") for f in factions()}
    out["shulgan"] = None
    return out


def new_heroes() -> list[dict]:
    """Roster heroes converted to the DB/static hero format."""
    out = []
    for h in roster()["heroes"]:
        s = h["stats"]
        out.append({
            "code": h["code"], "name": h["name"], "title": h.get("title", ""), "faction_code": h["faction"],
            "class_code": h["class"], "rarity": h["rarity"], "base_hp": s["hp"], "base_atk": s["atk"],
            "base_def": s["def"], "base_spd": s["spd"], "model": h["code"], "lore": h.get("lore", ""),
            "role": h.get("role", ""), "is_enemy": False, "summonable": h.get("summonable", True),
            "skill": {"kind": "kit", "name": h["ultimate"]["name"], "desc": h["ultimate"]["desc"]},
            "kit": {k: h[k] for k in ("basic", "skills", "ultimate", "passive", "mechanic")},
            "extra": {"crit": s.get("crit", 0.1), "crit_dmg": s.get("crit_dmg", 1.5), "growth": h.get("growth", {}),
                      "range": h.get("range"), "role_name": h.get("role_name", ""),
                      "appearance": h.get("appearance", ""), "personality": h.get("personality", "")},
        })
    return out


def legacy_kit(skill: dict, cls: str, rarity: int) -> dict:
    """Adapts a slice-0.1 single skill into the kit format (it becomes the ultimate)."""
    kind, power, name = skill.get("kind", "strike"), float(skill.get("power", 1.5)), skill.get("name", "")
    target = "lowest_hp_enemy" if cls == "ranger" else "target"
    if kind == "aoe":
        effects = [{"type": "damage", "target": "all_enemies", "mult": power}]
    elif kind == "heal":
        effects = [{"type": "heal", "target": "lowest_hp_ally", "mult": power * 1.6}]
        if rarity >= 6:
            effects.append({"type": "shield", "target": "same", "mult": power * 0.64})
    elif kind == "shield":
        effects = [{"type": "shield", "target": "lowest_hp_ally", "mult": power * 2.2}]
    elif kind == "stun":
        effects = [{"type": "damage", "target": "target", "mult": power}, {"type": "stun", "target": "target", "dur": 2.0}]
    else:
        effects = [{"type": "damage", "target": target, "mult": power}]
    return {
        "basic": {"name": "Атака", "desc": "", "effects": [{"type": "damage", "target": "target", "mult": 1.0}]},
        "skills": [],
        "ultimate": {"name": name, "desc": skill.get("desc", ""), "effects": effects},
        "passive": None,
        "mechanic": None,
    }
