"""Personality engine (stage 2): base archetype (data, editable) + individual traits, temperament, interests,
ambitions, habits, backstory and voice. Personalities evolve from victories, defeats, friendship, conflicts,
conversations and world events; noticeable changes create a new version with a checkpoint and a biography chapter.
Two personas of one archetype can behave completely differently: traits are drawn widely around the archetype bias."""
from __future__ import annotations

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AiArchetype, AiPersona, PlayerProfile
from . import memory as MEM
from . import tiers as TR

TRAITS = {"bravery": "Смелость", "patience": "Терпение", "sociability": "Общительность", "ambition": "Амбициозность",
          "generosity": "Щедрость", "curiosity": "Любопытство", "temper": "Вспыльчивость", "loyalty": "Верность"}
TRAIT_UP = {"bravery": "смелее", "patience": "терпеливее", "sociability": "общительнее", "ambition": "амбициознее",
            "generosity": "щедрее", "curiosity": "любопытнее", "temper": "вспыльчивее", "loyalty": "вернее своим"}
TRAIT_DOWN = {"bravery": "осторожнее", "patience": "нетерпеливее", "sociability": "замкнутее", "ambition": "спокойнее к рейтингам",
              "generosity": "бережливее", "curiosity": "равнодушнее к новому", "temper": "спокойнее", "loyalty": "независимее"}
AMBITIONS = {"arena_top": "Подняться в высшую лигу арены", "collector": "Собрать всех героев", "guild_pillar": "Стать опорой гильдии",
             "story": "Пройти всю историю Урала", "mentor": "Помогать новичкам", "raider": "Одолеть всех боссов",
             "treasurer": "Наполнить казну гильдии", "friends": "Найти верных друзей"}
HABITS = {"morning_hello": "Здоровается в чате", "boasts": "Хвастается победами", "breaks_after_loss": "Уходит отдохнуть после поражений",
          "revenge": "Ищет реванша у обидчиков", "silent_grinder": "Молча качается", "night_raids": "Любит боссов",
          "gift_giver": "Часто дарит подарки друзьям", "event_chaser": "Не пропускает события", "series_player": "Играет сериями"}
CATCHPHRASES = ["как говорил мой дед", "ну, держись", "по-уральски", "без паники", "эх, курай", "честно-честно",
                "вот так вот", "клянусь Иремелем", "ну ты понял", "спокойно, работаем", "кумыс в помощь", "йоу"]
EMOJIS = ["🙂", "😄", "😎", "🔥", "💪", "🤝", "😅", "🏔", "⚔️", "✨"]

DEFAULT_ARCHETYPES = {
    "competitor": ("Соперник", "Любит арену и рейтинги", {"ambition": 0.25, "bravery": 0.15, "temper": 0.1}, ["arena_top", "raider"]),
    "collector": ("Коллекционер", "Собирает героев и считает шансы призыва", {"patience": 0.2, "curiosity": 0.15}, ["collector", "story"]),
    "socializer": ("Душа компании", "Ради общения и гильдии", {"sociability": 0.3, "generosity": 0.15}, ["friends", "mentor", "guild_pillar"]),
    "strategist": ("Стратег", "Разбирает синергии фракций", {"patience": 0.2, "curiosity": 0.1, "temper": -0.15}, ["raider", "arena_top"]),
    "explorer": ("Исследователь", "Изучает регионы и сюжет", {"curiosity": 0.3, "patience": 0.1}, ["story", "collector"]),
    "newbie": ("Новичок", "Только начал путь", {"curiosity": 0.15, "bravery": -0.1}, ["story", "friends"]),
    "veteran": ("Ветеран", "Опора своей гильдии", {"loyalty": 0.3, "patience": 0.15, "generosity": 0.1}, ["guild_pillar", "mentor", "treasurer"]),
}

# event -> trait deltas and mood shift; "temper" decides whether a defeat teaches patience or burns it
EFFECTS = {
    "arena_win": ({"ambition": 0.012, "bravery": 0.01}, 0.18),
    "arena_loss": ({"bravery": -0.006}, -0.18),
    "friend": ({"sociability": 0.02, "generosity": 0.008}, 0.12),
    "conflict": ({"temper": 0.02, "loyalty": -0.006}, -0.15),
    "chat": ({"sociability": 0.004}, 0.03),
    "guild_join": ({"loyalty": 0.025, "sociability": 0.01}, 0.15),
    "guild_help": ({"loyalty": 0.006, "generosity": 0.004}, 0.04),
    "raid": ({"bravery": 0.008, "patience": 0.004}, 0.05),
    "event": ({"curiosity": 0.01}, 0.06),
    "gift": ({"generosity": 0.008}, 0.05),
    "tier_up": ({"ambition": 0.015}, 0.25),
}
VERSION_DRIFT = 0.15   # accumulated change that makes a new personality version


def _clamp(v: float) -> float:
    return round(max(0.02, min(0.98, v)), 3)


# ------------------------------------------------------------------ archetypes as data
def ensure_archetypes(db: Session) -> None:
    from ..social.ai.personas import ARCHETYPES
    have = {a.code for a in db.scalars(select(AiArchetype))}
    for code, a in ARCHETYPES.items():
        if code in have:
            continue
        name, desc, bias, amb = DEFAULT_ARCHETYPES.get(code, (code, a.get("desc", ""), {}, []))
        db.add(AiArchetype(code=code, name=name, description=desc, interests=list(a["interests"]), styles=list(a["styles"]),
                           trait_bias=bias, ambitions=amb, weight=1, enabled=True))
    db.flush()


def archetypes(db: Session) -> dict[str, AiArchetype]:
    rows = {a.code: a for a in db.scalars(select(AiArchetype))}
    if not rows:
        ensure_archetypes(db)
        rows = {a.code: a for a in db.scalars(select(AiArchetype))}
    return rows


def pick_archetype(db: Session, rng: random.Random) -> AiArchetype:
    rows = [a for a in archetypes(db).values() if a.enabled and a.weight > 0] or list(archetypes(db).values())
    return rng.choices(rows, weights=[max(1, a.weight) for a in rows])[0]


# ------------------------------------------------------------------ generation
def generate(rng: random.Random, arch: AiArchetype | None) -> dict:
    bias = (arch.trait_bias if arch else {}) or {}
    traits = {t: _clamp(rng.betavariate(2, 2) + float(bias.get(t, 0)) + rng.uniform(-0.05, 0.05)) for t in TRAITS}
    pool = list((arch.ambitions if arch else []) or []) + list(AMBITIONS)
    ambitions: list[str] = []
    while len(ambitions) < rng.choice([1, 2, 2, 3]):
        a = rng.choice(pool[:4] if rng.random() < 0.65 and pool[:4] else pool)
        if a not in ambitions and a in AMBITIONS:
            ambitions.append(a)
    habits = rng.sample(list(HABITS), rng.choice([1, 2, 2, 3]))
    if traits["temper"] > 0.65 and "revenge" not in habits and rng.random() < 0.6:
        habits.append("revenge")
    if traits["patience"] < 0.35 and "breaks_after_loss" not in habits and rng.random() < 0.6:
        habits.append("breaks_after_loss")
    voice = {"emoji": round(rng.uniform(0, 0.6) * (0.5 + traits["sociability"]), 2),
             "exclaim": round(rng.uniform(0, 0.5) * (0.5 + traits["temper"]), 2),
             "lowercase": rng.random() < 0.3, "ellipsis": rng.random() < 0.2,
             "catchphrase": rng.choice(CATCHPHRASES) if rng.random() < 0.45 else None,
             "emoji_set": rng.sample(EMOJIS, 3)}
    return {"traits": traits, "ambitions": ambitions, "habits": habits, "voice": voice,
            "mood": round(rng.uniform(-0.1, 0.3), 2)}


def apply_generated(persona: AiPersona, g: dict) -> None:
    persona.traits, persona.ambitions, persona.habits = g["traits"], g["ambitions"], g["habits"]
    persona.voice, persona.mood = g["voice"], g["mood"]
    persona.counters = persona.counters or {}


def ensure(db: Session, limit: int = 50) -> int:
    """Gives personas created before phase 3 a personality and a tier (deterministic per persona; the level and the
    whole game progress stay exactly as they were)."""
    rows = list(db.scalars(select(AiPersona).where((AiPersona.tier.is_(None))).limit(limit)))
    if not rows:
        return 0
    archs = archetypes(db)
    for p in rows:
        rng = random.Random(p.id)
        if not p.traits:
            apply_generated(p, generate(rng, archs.get(p.archetype)))
        prof = db.get(PlayerProfile, p.user_id)
        p.tier = TR.for_level(prof.level if prof else 1)
        p.pace = round(TR.TIERS[p.tier]["pace"] * rng.uniform(0.85, 1.15), 2)
        p.personality_version = max(1, p.personality_version or 0)
        MEM.checkpoint(db, p, "Характер сформирован (фаза 3)")
        if not (MEM.bio(db, p).entries or []):
            MEM.bio_add(db, p, "created", (p.backstory or "Пришёл в Уралию.") + f" Сейчас — {TR.TIERS[p.tier]['name'].lower()}.")
    db.flush()
    return len(rows)


# ------------------------------------------------------------------ evolution
def evolve(db: Session, persona: AiPersona, event: str, note: str | None = None) -> bool:
    """Applies an experience. Returns True when it produced a new personality version."""
    if event not in EFFECTS or not persona.traits:
        return False
    deltas, mood = EFFECTS[event]
    traits = dict(persona.traits)
    if event == "arena_loss":  # calm personas learn patience from defeats, hot-tempered ones lose it
        deltas = {**deltas, "patience": 0.008 if traits.get("temper", 0.5) < 0.5 else -0.01,
                  "temper": 0.006 if traits.get("temper", 0.5) >= 0.5 else 0.0}
    counters = dict(persona.counters or {})
    drift = dict(counters.get("drift") or {})
    for t, d in deltas.items():
        if t in traits and d:
            new = _clamp(traits[t] + d)
            drift[t] = round(drift.get(t, 0.0) + (new - traits[t]), 4)
            traits[t] = new
    persona.traits = traits
    persona.mood = round(max(-1.0, min(1.0, (persona.mood or 0.0) * 0.85 + mood)), 3)
    big = {t: v for t, v in drift.items() if abs(v) >= VERSION_DRIFT}
    changed = False
    if big:
        words = [TRAIT_UP[t] if v > 0 else TRAIT_DOWN[t] for t, v in sorted(big.items(), key=lambda kv: -abs(kv[1]))]
        persona.personality_version = (persona.personality_version or 0) + 1
        text = "Стал " + ", ".join(words[:2]) + (f" ({note})" if note else "")
        MEM.add(db, persona, "personality", text, importance=3)
        MEM.bio_add(db, persona, "personality", text)
        MEM.checkpoint(db, persona, text, keep=MEM.SECTION.get(db)["snapshots_keep"])
        for t in big:
            drift[t] = 0.0
        changed = True
    counters["drift"] = drift
    persona.counters = counters
    return changed


def count(persona: AiPersona, key: str, delta: int = 1, reset: tuple = ()) -> int:
    c = dict(persona.counters or {})
    c[key] = int(c.get(key, 0)) + delta
    for r in reset:
        c[r] = 0
    persona.counters = c
    return c[key]


# ------------------------------------------------------------------ behaviour
def action_weights(persona: AiPersona, base: dict) -> dict:
    """How traits, ambitions, habits and mood shape what the persona wants to do now."""
    t = persona.traits or {}
    if not t:
        return base
    w = {k: float(v) for k, v in base.items()}
    g = t.get
    w["arena"] = w.get("arena", 0) + 4 * g("ambition", 0.5) + 2 * g("bravery", 0.5)
    w["chat"] = w.get("chat", 0) * (0.4 + g("sociability", 0.5))
    w["friend"] = w.get("friend", 0) + 2 * g("generosity", 0.5) + g("sociability", 0.5)
    w["guild"] = w.get("guild", 0) + 3 * g("loyalty", 0.5)
    w["raid"] = w.get("raid", 0) + 3 * g("bravery", 0.5)
    w["event"] = w.get("event", 0) + 3 * g("curiosity", 0.5)
    w["level"] = w.get("level", 0) + 2 * g("patience", 0.5)
    amb = {"arena_top": ("arena", 3), "collector": ("level", 3), "guild_pillar": ("guild", 3), "story": ("level", 2),
           "mentor": ("friend", 2), "raider": ("raid", 3), "treasurer": ("guild", 2), "friends": ("friend", 3)}
    for a in persona.ambitions or []:
        if a in amb:
            k, v = amb[a]
            w[k] = w.get(k, 0) + v
    habits = set(persona.habits or [])
    mood = persona.mood or 0.0
    if mood < -0.4 and "breaks_after_loss" in habits:
        w["arena"] *= 0.3   # stung by defeats: trains or chats instead of fighting
        w["level"] = w.get("level", 0) + 3
    if mood > 0.4 and "boasts" in habits:
        w["chat"] = w.get("chat", 0) + 3
    if "silent_grinder" in habits:
        w["chat"] *= 0.5
        w["level"] = w.get("level", 0) + 2
    if "event_chaser" in habits:
        w["event"] = w.get("event", 0) + 3
    if "night_raids" in habits:
        w["raid"] = w.get("raid", 0) + 2
    if "gift_giver" in habits:
        w["friend"] = w.get("friend", 0) + 2
    return {k: max(0.1, v) for k, v in w.items()}


def wants_break(persona: AiPersona, rng: random.Random) -> bool:
    """After a series of defeats an impatient persona leaves the game for a while (ends its session)."""
    c = persona.counters or {}
    t = persona.traits or {}
    return (int(c.get("losses_row", 0)) >= 3 and t.get("patience", 0.5) < 0.45 and
            ("breaks_after_loss" in (persona.habits or []) or rng.random() < 0.3))


def describe(persona: AiPersona) -> dict:
    return {"traits": [{"code": k, "name": TRAITS[k], "value": (persona.traits or {}).get(k)} for k in TRAITS],
            "ambitions": [{"code": a, "name": AMBITIONS.get(a, a)} for a in persona.ambitions or []],
            "habits": [{"code": h, "name": HABITS.get(h, h)} for h in persona.habits or []],
            "voice": persona.voice or {}, "mood": persona.mood, "version": persona.personality_version,
            "tier": persona.tier, "tier_name": TR.TIERS.get(persona.tier or "", {}).get("name"), "pace": persona.pace,
            "counters": {k: v for k, v in (persona.counters or {}).items() if k != "drift"}}


def distribution(db: Session) -> dict:
    return dict(db.execute(select(AiPersona.tier, func.count()).group_by(AiPersona.tier)).all())
