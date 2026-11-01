"""Guild alliances (decision D-12) — a game feature for every guild: up to 3 guilds, a shared alliance chat
(`alliance:<id>`), allies are never matched against each other in guild wars. Leaders and deputies ("edit" right)
propose, accept, decline and leave. AI guilds answer proposals by their relations and reputation (stage 9)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..models import Guild, GuildAlliance, GuildAllianceMember, GuildAllianceProposal, GuildWar
from .guilds import guild_brief, log, my_guild

router = APIRouter(prefix="/alliances", tags=["alliances"])
MAX_GUILDS = 3


def alliance_of(db: Session, guild_id: str) -> GuildAlliance | None:
    am = db.get(GuildAllianceMember, guild_id)
    return db.get(GuildAlliance, am.alliance_id) if am else None


def allies(db: Session, guild_id: str) -> list[str]:
    a = alliance_of(db, guild_id)
    if a is None:
        return []
    return [g for g in db.scalars(select(GuildAllianceMember.guild_id).where(GuildAllianceMember.alliance_id == a.id))
            if g != guild_id]


def member_guilds(db: Session, alliance_id: str) -> list[Guild]:
    ids = list(db.scalars(select(GuildAllianceMember.guild_id).where(GuildAllianceMember.alliance_id == alliance_id)))
    return [g for g in (db.get(Guild, i) for i in ids) if g is not None]


def _system(db: Session, alliance: GuildAlliance, text: str) -> None:
    from .chat import system_message
    system_message(db, f"alliance:{alliance.id}", text)


def _at_war(db: Session, a: str, b: str) -> bool:
    return db.scalar(select(GuildWar.id).where(GuildWar.status == "active", ((GuildWar.guild_a == a) & (GuildWar.guild_b == b)) |
                                               ((GuildWar.guild_a == b) & (GuildWar.guild_b == a)))) is not None


def check_proposal(db: Session, g_from: Guild, g_to: Guild) -> None:
    if g_from.id == g_to.id:
        raise GameError("same_guild", "Нельзя заключить союз с собственной гильдией", 400)
    a1, a2 = alliance_of(db, g_from.id), alliance_of(db, g_to.id)
    if a1 is not None and a2 is not None:
        raise GameError("both_allied", "Обе гильдии уже в союзах" if a1.id != a2.id else "Гильдии уже союзники", 409)
    target = a1 or a2
    if target is not None and len(member_guilds(db, target.id)) >= MAX_GUILDS:
        raise GameError("alliance_full", f"В союзе уже {MAX_GUILDS} гильдии", 409)
    if _at_war(db, g_from.id, g_to.id):
        raise GameError("at_war", "Гильдии сейчас воюют друг с другом", 409)


def form(db: Session, g_from: Guild, g_to: Guild, actor: str | None) -> GuildAlliance:
    """Creates the alliance or adds the guild to the existing one."""
    check_proposal(db, g_from, g_to)
    a = alliance_of(db, g_from.id) or alliance_of(db, g_to.id)
    if a is None:
        a = GuildAlliance(name=f"Союз {g_from.tag} и {g_to.tag}"[:48], founder_guild_id=g_from.id, created_at=utcnow())
        db.add(a)
        db.flush()
    for g in (g_from, g_to):
        if db.get(GuildAllianceMember, g.id) is None:
            db.add(GuildAllianceMember(guild_id=g.id, alliance_id=a.id, joined_at=utcnow()))
    db.flush()
    for g, other in ((g_from, g_to), (g_to, g_from)):
        log(db, g.id, actor, "alliance_join", None, alliance=a.name, with_guild=other.name)
    _system(db, a, f"🤝 Гильдии «{g_from.name}» и «{g_to.name}» теперь в союзе «{a.name}».")
    return a


def leave_alliance(db: Session, g: Guild, actor: str | None) -> None:
    am = db.get(GuildAllianceMember, g.id)
    if am is None:
        raise GameError("no_alliance", "Гильдия не состоит в союзе", 404)
    a = db.get(GuildAlliance, am.alliance_id)
    db.delete(am)
    db.flush()
    log(db, g.id, actor, "alliance_leave", None, alliance=a.name)
    rest = member_guilds(db, a.id)
    _system(db, a, f"Гильдия «{g.name}» вышла из союза.")
    if len(rest) <= 1:  # an alliance of one is no alliance
        for other in rest:
            db.delete(db.get(GuildAllianceMember, other.id))
            log(db, other.id, None, "alliance_dissolved", None, alliance=a.name)
        db.flush()
        db.delete(a)


def view(db: Session, guild_id: str) -> dict:
    a = alliance_of(db, guild_id)
    def _p(p: GuildAllianceProposal, other_id: str) -> dict:
        og = db.get(Guild, other_id)
        return {"id": p.id, "guild": guild_brief(db, og) if og else None, "at": as_utc(p.created_at).isoformat()}
    incoming = db.scalars(select(GuildAllianceProposal).where(GuildAllianceProposal.to_guild_id == guild_id,
                                                              GuildAllianceProposal.status == "pending"))
    outgoing = db.scalars(select(GuildAllianceProposal).where(GuildAllianceProposal.from_guild_id == guild_id,
                                                              GuildAllianceProposal.status == "pending"))
    return {"alliance": {"id": a.id, "name": a.name, "channel": f"alliance:{a.id}",
                         "guilds": [guild_brief(db, g) for g in member_guilds(db, a.id)]} if a else None,
            "incoming": [_p(p, p.from_guild_id) for p in incoming], "outgoing": [_p(p, p.to_guild_id) for p in outgoing],
            "max_guilds": MAX_GUILDS}


# ------------------------------------------------------------------ player API
@router.get("/mine")
def mine(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id)
    from .guilds import can
    return {**view(db, g.id), "can_manage": can(m.role, "edit")}


class ProposeIn(BaseModel):
    guild_id: str = Field(max_length=36)


@router.post("/propose")
def propose(body: ProposeIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "edit", lock=True)
    og = db.get(Guild, body.guild_id)
    if og is None:
        raise GameError("not_found", "Гильдия не найдена", 404)
    check_proposal(db, g, og)
    if db.scalar(select(GuildAllianceProposal).where(GuildAllianceProposal.from_guild_id == g.id,
                                                     GuildAllianceProposal.to_guild_id == og.id,
                                                     GuildAllianceProposal.status == "pending")):
        return {"status": "pending", **view(db, g.id)}
    p = GuildAllianceProposal(from_guild_id=g.id, to_guild_id=og.id, status="pending", proposed_by=user.id,
                              created_at=utcnow())
    db.add(p)
    log(db, g.id, user.id, "alliance_propose", None, to_guild=og.name)
    log(db, og.id, None, "alliance_proposed", None, from_guild=g.name)
    db.flush()
    if og.is_ai:  # an AI guild answers by its relations and reputation
        from ..ai.guild_ai import consider_alliance
        if consider_alliance(db, og, g):
            p.status = "accepted"
            form(db, g, og, None)
        else:
            p.status = "declined"
            log(db, g.id, None, "alliance_declined", None, by_guild=og.name)
    db.commit()
    return {"status": p.status, **view(db, g.id)}


@router.post("/proposals/{proposal_id}/{action}")
def respond(proposal_id: str, action: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if action not in ("accept", "decline", "cancel"):
        raise GameError("bad_action", "Действие: accept, decline или cancel", 400)
    g, m = my_guild(db, user.id, "edit", lock=True)
    p = db.get(GuildAllianceProposal, proposal_id)
    if p is None or p.status != "pending":
        raise GameError("not_found", "Предложение не найдено", 404)
    if action == "cancel":
        if p.from_guild_id != g.id:
            raise GameError("forbidden", "Отменить может только предложившая гильдия", 403)
        p.status = "cancelled"
    else:
        if p.to_guild_id != g.id:
            raise GameError("forbidden", "Ответить может только приглашённая гильдия", 403)
        if action == "accept":
            form(db, db.get(Guild, p.from_guild_id), g, user.id)
            p.status = "accepted"
        else:
            p.status = "declined"
            log(db, p.from_guild_id, user.id, "alliance_declined", None, by_guild=g.name)
    db.commit()
    return view(db, g.id)


@router.post("/leave")
def leave(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "edit", lock=True)
    leave_alliance(db, g, user.id)
    db.commit()
    return view(db, g.id)


class RenameIn(BaseModel):
    name: str = Field(min_length=3, max_length=48)


@router.post("/rename")
def rename(body: RenameIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    g, m = my_guild(db, user.id, "edit", lock=True)
    a = alliance_of(db, g.id)
    if a is None:
        raise GameError("no_alliance", "Гильдия не состоит в союзе", 404)
    from .guilds import _check_text
    _check_text(body.name)
    a.name = body.name.strip()
    log(db, g.id, user.id, "alliance_rename", None, name=a.name)
    _system(db, a, f"Союз переименован: «{a.name}».")
    db.commit()
    return view(db, g.id)
