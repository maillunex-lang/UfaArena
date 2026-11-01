"""PvP, events and AI-organised activities (stages 10 and 13; decisions D-03, D-05).

* Arena: AI choose allowed opponents by analysing them (power and faction advantage) at the configured difficulty,
  keep a daily fight limit, rebuild the team after losing streaks and remember results (memory, relationships).
* Rankings: AI may be shown in the common tables with the "AI" label when the admin enables it; places and rewards
  stay for real players only (D-03).
* World events: AI contribute as a separate "AI residents' contribution" line, at most `share_pct` of the goal (≤ 20%),
  never in personal/guild tops and never rewarded (D-05).
* AI-organised activities: weekly internal competitions in AI guilds and friendly tournaments inside informal groups
  (results posted in their chats; no rewards)."""
from __future__ import annotations

import random
import secrets

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AiPersona, ArenaProfile, PlayerProfile, WorldEvent
from .sections import Section

PVP = Section(
    "ai_pvp",
    {"arena_fights_per_day": 6, "difficulty": "fair", "analyze": True, "rebuild_after_losses": 3,
     "tournaments": True, "ai_in_rankings": False},
    {"arena_fights_per_day": ("int", 0, 50), "difficulty": ("choice", ["easy", "fair", "challenging"]),
     "analyze": ("bool",), "rebuild_after_losses": ("int", 1, 10), "tournaments": ("bool",), "ai_in_rankings": ("bool",)},
    {"arena_fights_per_day": "Боёв на арене в день на ИИ, максимум",
     "difficulty": "Подбор соперников: easy — слабее, fair — равные, challenging — сильнее",
     "analyze": "Анализировать соперника перед боем (сила, преимущество фракций)",
     "rebuild_after_losses": "Перестраивать защиту после стольких поражений подряд",
     "tournaments": "ИИ дополняют сетки турниров (с меткой «ИИ», без наград)",
     "ai_in_rankings": "Показывать ИИ в общих рейтингах с меткой «ИИ» (места и награды — только игрокам)"})
EVENTS = Section(
    "ai_events",
    {"contribute": True, "share_pct": 20, "points_per_action": 40, "guild_contests": True, "friendly_tournaments": True},
    {"contribute": ("bool",), "share_pct": ("int", 0, 20), "points_per_action": ("int", 1, 10000),
     "guild_contests": ("bool",), "friendly_tournaments": ("bool",)},
    {"contribute": "ИИ вносят вклад в мировые события (отдельной строкой)",
     "share_pct": "Вклад ИИ-жителей не больше, % цели события (до 20)",
     "points_per_action": "Очков вклада за одно участие ИИ (ориентир)",
     "guild_contests": "ИИ-гильдии проводят внутренние соревнования недели",
     "friendly_tournaments": "Круги друзей устраивают дружеские турниры (без наград)"})


# ------------------------------------------------------------------ arena
def analyze(db: Session, me: ArenaProfile, opp: ArenaProfile) -> float:
    """Expected strength ratio (>1 = I am stronger), with the faction advantage of the squads."""
    from ..game import roster as R
    adv = R.advantage()
    ratio = (me.defense_power or 1) / max(1, opp.defense_power or 1)
    mine = [u.get("faction_code") for u in (me.defense or []) if isinstance(u, dict)]
    theirs = [u.get("faction_code") for u in (opp.defense or []) if isinstance(u, dict)]
    edge = sum(1 for f in mine if adv.get(f) in theirs) - sum(1 for f in theirs if adv.get(f) in mine)
    return ratio * (1 + 0.04 * edge)


def pick_opponent(db: Session, persona: AiPersona, me: ArenaProfile, cands: list[ArenaProfile],
                  rng: random.Random) -> ArenaProfile | None:
    s = PVP.get(db)
    if not cands:
        return None
    if not s["analyze"]:
        return rng.choice(cands)
    want = {"easy": 1.25, "fair": 1.0, "challenging": 0.85}[s["difficulty"]]
    t = persona.traits or {}
    want *= 1 - 0.1 * (t.get("bravery", 0.5) - 0.5)  # brave personas pick harder fights
    return min(cands, key=lambda o: abs(analyze(db, me, o) - want) + rng.uniform(0, 0.05))


def arena_allowed(db: Session, persona: AiPersona) -> bool:
    from ..social.common import day
    c = dict(persona.counters or {})
    d = dict(c.get("daily") or {})
    if d.get("day") != day():
        d = {"day": day()}
    if int(d.get("arena", 0)) >= PVP.get(db)["arena_fights_per_day"]:
        return False
    d["arena"] = int(d.get("arena", 0)) + 1
    c["daily"] = d
    persona.counters = c
    return True


def maybe_rebuild_defense(db: Session, persona: AiPersona) -> bool:
    """After a losing streak the persona rebuilds its squad (and with it the arena defense)."""
    c = persona.counters or {}
    if int(c.get("losses_row", 0)) < PVP.get(db)["rebuild_after_losses"]:
        return False
    from . import play as PLAY
    from . import memory as MEM
    rng = random.Random()
    slots = PLAY.best_formation(db, persona, rng, variant=int(c.get("losses_row", 0)))
    from ..models import Formation
    f = db.get(Formation, (persona.user_id, "campaign"))
    if f is not None and any(slots):
        f.slots = slots
    from ..social.common import freeze_squad, squad_power
    ap = db.get(ArenaProfile, persona.user_id)
    if ap is not None:
        sq = freeze_squad(db, persona.user_id)
        ap.defense, ap.defense_power = sq, squad_power(sq)
    MEM.add(db, persona, "decision", "Перестроил отряд после серии поражений на арене", importance=2)
    cc = dict(persona.counters or {})
    cc["rebuilds"] = int(cc.get("rebuilds", 0)) + 1
    persona.counters = cc
    return True


# ------------------------------------------------------------------ world events (D-05)
def contribute_event(db: Session, persona: AiPersona) -> int:
    s = EVENTS.get(db)
    if not s["contribute"] or s["share_pct"] <= 0:
        return 0
    from ..social.events import active_events
    prof = db.get(PlayerProfile, persona.user_id)
    added = 0
    for ev in active_events(db):
        cap = int(ev.goal * min(20, s["share_pct"]) / 100)
        room = cap - int(ev.ai_progress or 0)
        if room <= 0:
            continue
        pts = min(room, max(1, int(s["points_per_action"] * (0.5 + (prof.level if prof else 1) / 80))))
        db.execute(update(WorldEvent).where(WorldEvent.id == ev.id)
                   .values(ai_progress=func.least(WorldEvent.ai_progress + pts, cap) if db.bind.dialect.name == "postgresql"
                           else func.min(WorldEvent.ai_progress + pts, cap))
                   .execution_options(synchronize_session=False))
        added += pts
    return added


# ------------------------------------------------------------------ AI-organised activities
def guild_contest(db: Session, g, rng: random.Random) -> str | None:
    """Weekly internal competition of an AI guild: the best contributors of the week are celebrated in the chat."""
    from ..models import GuildMember
    from ..social.common import week_key
    from . import guild_ai as GAI
    st = GAI.state(db, g)
    wk = week_key()
    if any(h.get("kind") == "contest" and h.get("week") == wk for h in (st.history or [])):
        return None
    top = list(db.scalars(select(GuildMember).where(GuildMember.guild_id == g.id).order_by(GuildMember.contribution_week.desc()).limit(3)))
    top = [m for m in top if (m.contribution_week or 0) > 0]
    if not top:
        return None
    names = [db.get(PlayerProfile, m.user_id).nickname for m in top]
    text = "🏅 Соревнование недели в гильдии: " + ", ".join(f"{i + 1}. {n}" for i, n in enumerate(names)) + ". Так держать!"
    from ..social.chat import system_message
    system_message(db, f"guild:{g.id}", text)
    GAI._hist(st, "contest", text, week=wk)
    return text


def friendly_tournament(db: Session, group, rng: random.Random) -> str | None:
    """A small round-robin of training fights inside an informal circle; the winner is announced in its chat."""
    from . import social as SOC
    from ..social.common import pvp
    ids = SOC.members(db, group.id)
    aps = [a for a in (db.get(ArenaProfile, u) for u in ids) if a is not None and a.defense and a.is_ai][:4]
    if len(aps) < 3:
        return None
    score = {a.user_id: 0 for a in aps}
    for i, a in enumerate(aps):
        for b in aps[i + 1:]:
            res = pvp(db, a.defense, b.defense, secrets.randbits(40))
            score[a.user_id if res["result"] == "victory" else b.user_id] += 1
            SOC.mutual(db, a.user_id, b.user_id, "chat")
    win = max(score, key=lambda k: score[k])
    name = db.get(PlayerProfile, win).nickname
    text = f"⚔️ Дружеский турнир круга «{group.name}»: побеждает {name}! (тренировочные бои, без наград)"
    from ..social.chat import system_message
    system_message(db, f"group:{group.id}", text)
    return text


def activities(db: Session, rng: random.Random) -> dict:
    s = EVENTS.get(db)
    out = {"contests": 0, "tournaments": 0}
    from ..models import AiSocialGroup, Guild
    if s["guild_contests"]:
        for g in db.scalars(select(Guild).where(Guild.is_ai.is_(True)).limit(10)):
            if guild_contest(db, g, rng):
                out["contests"] += 1
    if s["friendly_tournaments"] and rng.random() < 0.3:
        groups = list(db.scalars(select(AiSocialGroup).where(AiSocialGroup.active.is_(True)).order_by(func.random()).limit(1)))
        for gr in groups:
            if friendly_tournament(db, gr, rng):
                out["tournaments"] += 1
    db.flush()
    return out
