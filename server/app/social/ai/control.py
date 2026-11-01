"""Switches for AI participation at three levels:
- owner (admin, global): chat, raids, guild help, arena, guild wars, whether AI arena fights are rated;
- guild leader / deputy (per guild): recruit AI, AI officers help with management, AI in raids, AI in wars;
- player (personal): AI may attack my arena defense; show AI messages in chat.
An action happens only when every relevant level allows it."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import CurrentUser, player
from ...models import AdminAction, Guild, PlayerProfile, ServerSetting

GLOBAL_DEFAULT = {"chat": True, "raids": True, "guild_help": True, "arena": True, "guild_wars": True, "arena_rated": False}
GUILD_DEFAULT = {"recruit": True, "management": False, "raids": True, "wars": True}
PLAYER_DEFAULT = {"arena_defense": True, "show_ai_chat": True, "ai_contact": True}

GLOBAL_NAMES = {"chat": "ИИ общаются в чатах", "raids": "ИИ атакуют рейд-боссов", "guild_help": "ИИ помогают гильдиям",
                "arena": "ИИ сражаются на арене", "guild_wars": "ИИ участвуют в войнах гильдий",
                "arena_rated": "Бои ИИ на арене меняют рейтинг игроков"}
GUILD_NAMES = {"recruit": "Принимать ИИ-жителей в гильдию", "management": "ИИ-офицеры помогают управлять (заявки, постройки)",
               "raids": "ИИ-участники бьют босса гильдии", "wars": "ИИ-участники воюют за гильдию"}
PLAYER_NAMES = {"arena_defense": "ИИ могут атаковать мою защиту на арене (тренировочно)",
                "show_ai_chat": "Показывать сообщения ИИ в общем чате",
                "ai_contact": "ИИ-персонажи могут писать мне первыми и приглашать (гильдии, события)"}

router = APIRouter(tags=["ai-control"])


def global_switches(db: Session) -> dict:
    row = db.get(ServerSetting, "ai_switches")
    return {**GLOBAL_DEFAULT, **((row.value or {}) if row else {})}


def set_global(db: Session, changes: dict, who: str) -> dict:
    row = db.get(ServerSetting, "ai_switches")
    if row is None:
        row = ServerSetting(key="ai_switches", value={})
        db.add(row)
    row.value = {**(row.value or {}), **{k: bool(v) for k, v in changes.items() if k in GLOBAL_DEFAULT}}
    db.add(AdminAction(admin=who, action="ai_switches", details=changes))
    return global_switches(db)


def guild_policy(g: Guild | None) -> dict:
    return {**GUILD_DEFAULT, **((g.ai_policy or {}) if g else {})}


def player_prefs(p: PlayerProfile | None) -> dict:
    return {**PLAYER_DEFAULT, **((p.ai_prefs or {}) if p else {})}


def allowed(db: Session, area: str, guild: Guild | None = None, guild_key: str | None = None) -> bool:
    if not global_switches(db).get(area, False):
        return False
    if guild is not None and not guild.is_ai and guild_key:
        return bool(guild_policy(guild).get(guild_key, False))
    return True


# ------------------------------------------------------------------ player API
@router.get("/social/ai-prefs")
def get_prefs(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    return {"prefs": player_prefs(p), "names": PLAYER_NAMES, "global": global_switches(db), "global_names": GLOBAL_NAMES}


class PrefsIn(BaseModel):
    arena_defense: bool | None = None
    show_ai_chat: bool | None = None
    ai_contact: bool | None = None


@router.post("/social/ai-prefs")
def set_prefs(body: PrefsIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    p.ai_prefs = {**player_prefs(p), **{k: v for k, v in body.model_dump().items() if v is not None}}
    db.commit()
    return {"prefs": player_prefs(p)}


class GuildPolicyIn(BaseModel):
    recruit: bool | None = None
    management: bool | None = None
    raids: bool | None = None
    wars: bool | None = None


@router.post("/guilds/ai-policy")
def set_guild_policy(body: GuildPolicyIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    from ..guilds import log, my_guild
    g, m = my_guild(db, user.id, "edit", lock=True)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    g.ai_policy = {**guild_policy(g), **changes}
    log(db, g.id, user.id, "ai_policy", None, **changes)
    db.commit()
    return {"policy": guild_policy(g)}
