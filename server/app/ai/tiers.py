"""Power tiers of the AI population (stage 4): newcomers, regular players, experienced, veterans and the elite differ
in level, power, hero collection, stars, development pace and strategy. Progress adapts to the real world (levels of
active real players), never to one particular player.

Spec §7 has priority over "VIP" in stage 4: VIP in this project comes from purchases, so an AI with VIP would be a fake
evidence of payments. AI personas therefore always keep VIP 0 (recorded in URALIA_AI_DECISIONS.md, P3-01)."""
from __future__ import annotations

import random
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..game import data as D
from ..models import PlayerProfile
from .sections import Section

CAP = D.LEVEL_CAP_MVP

TIERS = {
    "newbie":      {"name": "Новичок", "lvl": (1, 12),  "heroes": (4, 7),   "stars": (0, 0), "pace": 0.6,
                    "strategies": ["balanced"], "desc": "Только начинают: несколько героев, медленный рост"},
    "regular":     {"name": "Обычный игрок", "lvl": (10, 28), "heroes": (6, 10), "stars": (0, 1), "pace": 1.0,
                    "strategies": ["balanced", "aggressive"], "desc": "Играют регулярно, команда собрана"},
    "experienced": {"name": "Опытный", "lvl": (25, 42), "heroes": (9, 14), "stars": (0, 2), "pace": 1.2,
                    "strategies": ["balanced", "aggressive", "defensive"], "desc": "Знают синергии, следят за ареной"},
    "veteran":     {"name": "Ветеран", "lvl": (38, 62), "heroes": (12, 18), "stars": (1, 3), "pace": 1.4,
                    "strategies": ["defensive", "balanced", "aggressive"], "desc": "Опора гильдий, большая коллекция"},
    "elite":       {"name": "Элита", "lvl": (55, 80), "heroes": (15, 22), "stars": (2, 4), "pace": 1.7,
                    "strategies": ["aggressive", "defensive"], "desc": "Вершина рейтингов, максимум усилий"},
}
ORDER = list(TIERS)
STRATEGY_NAMES = {"balanced": "Сбалансированная", "aggressive": "Атакующая", "defensive": "Оборонительная"}

SECTION = Section("ai_tiers",
                  {"newbie": 25, "regular": 35, "experienced": 22, "veteran": 13, "elite": 5, "world_adapt": True,
                   "world_margin": 8},
                  {**{k: ("int", 0, 100) for k in TIERS}, "world_adapt": ("bool",), "world_margin": ("int", 0, 60)},
                  {**{k: "Доля: " + v["name"] for k, v in TIERS.items()}, "world_adapt": "Подстраиваться под уровень мира",
                   "world_margin": "Насколько ИИ слоёв до «опытного» могут обгонять реальных игроков, уровней"})


def clamp_level(lv: int) -> int:
    return max(1, min(CAP, lv))


def tier_range(code: str) -> tuple[int, int]:
    lo, hi = TIERS[code]["lvl"]
    return clamp_level(lo), clamp_level(hi)


def pick(rng: random.Random, weights: dict) -> str:
    w = [max(0, int(weights.get(k, 0))) for k in ORDER]
    if sum(w) <= 0:
        w = [1] * len(ORDER)
    return rng.choices(ORDER, weights=w)[0]


def for_level(level: int) -> str:
    """Tier of an existing persona from its level (used once for personas created before phase 3)."""
    best = "newbie"
    for code in ORDER:
        if level >= tier_range(code)[0]:
            best = code
    return best


def level_for(rng: random.Random, tier: str, arch_range: tuple[int, int] | None = None) -> int:
    lo, hi = tier_range(tier)
    if arch_range:
        a, b = max(lo, arch_range[0]), min(hi, arch_range[1])
        if a <= b and rng.random() < 0.7:  # archetype flavours the level inside the tier
            lo, hi = a, b
    return rng.randint(lo, hi)


_world_cache: dict = {"at": 0.0, "value": None}


def world_level(db: Session) -> int | None:
    """Typical level of real players active in the last 14 days (90th percentile), cached for 10 minutes."""
    if time.monotonic() - _world_cache["at"] < 600 and _world_cache["value"] is not None:
        return _world_cache["value"]
    since = utcnow() - timedelta(days=14)
    levels = sorted(db.scalars(select(PlayerProfile.level).where(PlayerProfile.is_ai.is_(False),
                                                                 PlayerProfile.last_seen_at >= since)).all())
    value = levels[min(len(levels) - 1, int(len(levels) * 0.9))] if levels else None
    _world_cache.update(at=time.monotonic(), value=value)
    return value


def level_cap(db: Session, tier: str, s: dict | None = None) -> int:
    """Where this tier's growth stops. Lower tiers stay near the real world (no artificial runaway), veterans and the
    elite may lead it — but only up to their tier range."""
    s = s or SECTION.get(db)
    hi = tier_range(tier)[1]
    if not s.get("world_adapt", True) or tier in ("veteran", "elite"):
        return hi
    w = world_level(db)
    if w is None:
        return hi
    return max(tier_range(tier)[0], min(hi, w + int(s.get("world_margin", 8))))


def next_tier(tier: str) -> str | None:
    i = ORDER.index(tier) if tier in ORDER else 0
    return ORDER[i + 1] if i + 1 < len(ORDER) else None
