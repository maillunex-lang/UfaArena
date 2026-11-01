"""Read-only aggregate for the home dashboard and the notification centre (one request instead of many).
It only reads existing systems; no game logic lives here."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player
from ..models import (
    ChatMessage, ChatRead, FriendGift, FriendRequest, GuildApplication, GuildMember, PlayerCampaignProgress,
    PlayerProfile, WorldEvent,
)
from ..services import afk_preview, ordered_nodes

router = APIRouter(tags=["hub"])


@router.get("/player/summary")
def summary(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    from .economy import _mail_list, _quest_list
    p = db.get(PlayerProfile, user.id)
    quests = _quest_list(db, user.id)
    mail = _mail_list(db, user.id)
    afk = afk_preview(db, p)
    nodes = ordered_nodes(db)
    cleared = set(db.scalars(select(PlayerCampaignProgress.node_code).where(PlayerCampaignProgress.user_id == user.id)))
    nxt = next((n for n in nodes if n.code not in cleared), None)
    gm = db.scalar(select(GuildMember).where(GuildMember.user_id == user.id))
    guild_apps = 0
    if gm is not None and gm.role in ("leader", "deputy", "officer"):
        guild_apps = db.scalar(select(func.count()).select_from(GuildApplication).where(
            GuildApplication.guild_id == gm.guild_id, GuildApplication.kind == "application",
            GuildApplication.status == "pending")) or 0
    chans = ["global"] + ([f"guild:{gm.guild_id}"] if gm else [])
    unread = 0
    for ch in chans:
        r = db.get(ChatRead, (user.id, ch))
        unread += db.scalar(select(func.count()).select_from(ChatMessage).where(
            ChatMessage.channel == ch, ChatMessage.id > (r.last_id if r else 0), ChatMessage.hidden.is_(False),
            or_(ChatMessage.user_id.is_(None), ChatMessage.user_id != user.id))) or 0
    now = utcnow()
    events = [{"id": e.id, "name": e.name, "progress": e.progress, "goal": e.goal, "ends_at": as_utc(e.ends_at).isoformat()}
              for e in db.scalars(select(WorldEvent).where(WorldEvent.status == "active", WorldEvent.ends_at > now))]
    daily = [q for q in quests if q["kind"] == "daily"]
    return {
        "quests": {"claimable": sum(1 for q in quests if q["claimable"]), "daily_done": sum(1 for q in daily if q["claimed"] or q["claimable"]),
                   "daily_total": len(daily), "daily": daily[:4]},
        "mail_unclaimed": sum(1 for m in mail if not m["claimed"] and m["attachments"]),
        "mail_unread": sum(1 for m in mail if not m["claimed"]),
        "afk": {"hours": round(afk["credited_s"] / 3600, 1), "cap_hours": round(afk["cap_s"] / 3600), "rewards": afk["rewards"],
                "full": afk["credited_s"] >= afk["cap_s"]},
        "campaign": {"cleared": len(cleared), "total": len(nodes),
                     "next": {"code": nxt.code, "name": nxt.name} if nxt else None},
        "social": {
            "friend_requests": db.scalar(select(func.count()).select_from(FriendRequest).where(
                FriendRequest.to_id == user.id, FriendRequest.status == "pending")) or 0,
            "gifts": db.scalar(select(func.count()).select_from(FriendGift).where(
                FriendGift.to_id == user.id, FriendGift.claimed_at.is_(None))) or 0,
            "chat_unread": min(99, unread), "guild_apps": guild_apps, "in_guild": gm is not None,
        },
        "events": events,
    }
