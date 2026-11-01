"""Task handlers: the Director decides *what* and *when*; these modules do the work through the same game code the
players' API uses (decision D-01) — no rules are duplicated here. Phase 2 wires the existing v1 behaviours; later
phases replace them with the Progression / PvP / Social / Economy engines without changing the queue."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy.orm import Session

from ..core.db import utcnow
from ..models import AiPersona, AiTask, PlayerProfile

_rng = random.Random()


def _act(db: Session, t: AiTask) -> dict:
    from ..social.ai import population as V1
    from ..social.common import day
    persona = db.get(AiPersona, t.persona_id)
    if persona is None or not persona.active:
        return {"skipped": "persona disabled"}
    prof = db.get(PlayerProfile, persona.user_id)
    if persona.day != day():
        persona.day, persona.actions_today = day(), 0
    if persona.actions_today >= V1.AI()["max_actions_per_persona_day"]:
        return {"skipped": "daily cap"}
    action = t.kind.split(":", 1)[1]
    prof.last_seen_at = utcnow()  # presence follows the persona's own session
    V1.ACTIONS[action](db, persona, prof)
    persona.actions_today += 1
    persona.last_action_at = utcnow()
    from . import personality as PERS
    if PERS.wants_break(persona, _rng):  # stung by a series of defeats: leaves the game for a while
        persona.session_until = utcnow()
        PERS.count(persona, "breaks")
        PERS.count(persona, "losses_row", delta=0, reset=("losses_row",))
        V1.log(db, persona, "break", reason="losses")
        return {"action": action, "break": True}
    return {"action": action}


def _dm(db: Session, t: AiTask) -> dict:
    from ..social.ai import population as V1
    from ..social.ai.control import global_switches
    if not global_switches(db).get("chat", True):
        return {"skipped": "chat off"}
    pl = t.payload or {}
    return {"replied": V1.handle_dm(db, pl.get("persona_user_id", ""), pl.get("to_user", ""), pl.get("channel"), pl.get("text", ""))}


def _mention(db: Session, t: AiTask) -> dict:
    from ..social.ai import population as V1
    from ..social.ai.control import global_switches
    if not global_switches(db).get("chat", True):
        return {"skipped": "chat off"}
    pl = t.payload or {}
    return {"replied": V1.handle_mention(db, pl.get("channel", "global"), pl.get("user_id", ""), pl.get("text", ""))}


def _chat_keepalive(db: Session, t: AiTask) -> dict:
    from ..social.ai import banter, population as V1
    return {"chat": banter.keep_alive(db, V1.AI()), "reactions": banter.react_sometimes(db)}


def _play(db: Session, t: AiTask) -> dict:
    """A play session by the game rules (stages 5, 12; decision D-02)."""
    from ..social.ai import population as V1
    from ..social.common import day
    from . import play as PLAY
    persona = db.get(AiPersona, t.persona_id)
    if persona is None or not persona.active:
        return {"skipped": "persona disabled"}
    if persona.day != day():
        persona.day, persona.actions_today = day(), 0
    if persona.actions_today >= V1.AI()["max_actions_per_persona_day"]:
        return {"skipped": "daily cap"}
    prof = db.get(PlayerProfile, persona.user_id)
    prof.last_seen_at = utcnow()
    persona.actions_today += 1
    persona.last_action_at = utcnow()
    db.commit()
    res = PLAY.session(db, persona, str(t.id), _rng)
    from . import personality as PERS
    if PERS.wants_break(persona, _rng):
        persona.session_until = utcnow()
    db.commit()
    return res


HANDLERS = {"dm": _dm, "mention": _mention, "chat_keepalive": _chat_keepalive, "play": _play}


def run(db: Session, t: AiTask) -> dict:
    if t.kind.startswith("act:"):
        return _act(db, t)
    fn = HANDLERS.get(t.kind)
    if fn is None:
        raise ValueError(f"unknown task kind {t.kind}")
    return fn(db, t)


def next_action_delay(persona: AiPersona, peak: bool) -> timedelta:
    talk = (persona.temperament or {}).get("talkative", 0.5)
    minutes = _rng.randint(8, 50) / max(0.3, talk)
    return timedelta(minutes=minutes / (1.6 if peak else 1.0))
