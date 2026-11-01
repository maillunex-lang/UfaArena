"""Story choices and flags (lore stage S2). The server is authoritative: it validates that a choice exists, that the
player has reached it, and that it was not made before; the client only shows options and the resulting lines.

Story lines on campaign stages may carry:
  {"choice": "<choice_id>"}               — show the options of this choice at this point of the scene;
  {"if": {"<flag>": "<value>"}, ...line}  — show the line only when the flag has this value.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import PlayerCampaignProgress, PlayerStoryFlag, StoryChoice

router = APIRouter(prefix="/story", tags=["story"])
PATH = Path(__file__).resolve().parents[1] / "game" / "content" / "story.json"


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def choices() -> dict:
    return registry()["choices"]


def flags_of(db: Session, user_id: str) -> dict[str, str]:
    return {f.flag: f.value for f in db.scalars(select(PlayerStoryFlag).where(PlayerStoryFlag.user_id == user_id))}


def set_flags(db: Session, user_id: str, flags: dict, source: str) -> None:
    for k, v in flags.items():
        row = db.get(PlayerStoryFlag, (user_id, k))
        if row is None:
            db.add(PlayerStoryFlag(user_id=user_id, flag=k, value=str(v), source=source))
        else:
            row.value, row.source, row.set_at = str(v), source, utcnow()


def _choice_view(cid: str, c: dict, made: StoryChoice | None, cleared: set[str]) -> dict:
    req = c.get("requires_cleared")
    return {"id": cid, "scene": c["scene"], "title": c["title"], "prompt": c["prompt"],
            "available": not req or req in cleared,
            "options": [{"key": k, "text": o["text"]} for k, o in c["options"].items()],
            "made": made.option if made else None, "made_at": as_utc(made.made_at).isoformat() if made else None}


@router.get("/state")
def state(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    made = {c.choice_id: c for c in db.scalars(select(StoryChoice).where(StoryChoice.user_id == user.id))}
    cleared = set(db.scalars(select(PlayerCampaignProgress.node_code).where(PlayerCampaignProgress.user_id == user.id)))
    return {"flags": flags_of(db, user.id),
            "choices": [_choice_view(cid, c, made.get(cid), cleared) for cid, c in choices().items()]}


class ChoiceIn(BaseModel):
    choice_id: str = Field(max_length=64)
    option: str = Field(max_length=32)


@router.post("/choice")
def make_choice(body: ChoiceIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                db: Session = Depends(get_db)):
    c = choices().get(body.choice_id)
    if c is None:
        raise GameError("not_found", "Нет такого выбора", 404)
    opt = c["options"].get(body.option)
    if opt is None:
        raise GameError("bad_option", "Нет такого варианта", 400)

    def do():
        req = c.get("requires_cleared")
        if req and db.get(PlayerCampaignProgress, (user.id, req)) is None:
            raise GameError("choice_locked", "Этот выбор ещё впереди", 403)
        prev = db.get(StoryChoice, (user.id, body.choice_id))
        if prev is not None:
            if prev.option == body.option:  # repeated request (e.g. replayed scene): same answer is fine
                return {"choice_id": body.choice_id, "option": prev.option, "flags": flags_of(db, user.id)}
            raise GameError("already_chosen", "Решение уже принято — его не изменить", 409)
        db.add(StoryChoice(user_id=user.id, choice_id=body.choice_id, option=body.option))
        set_flags(db, user.id, opt.get("flags", {}), f"choice:{body.choice_id}")
        db.flush()
        from ..core.audit import audit
        audit(db, user.id, "story.choice", None, choice=body.choice_id, option=body.option)
        return {"choice_id": body.choice_id, "option": body.option, "flags": flags_of(db, user.id)}

    return run_idempotent(db, user.id, key, f"story_choice:{body.choice_id}", body.model_dump(), do)
