"""Chat: global, guild and private channels; filter, flood control, reactions, unread counters, reports.
Delivery is polling (`after` cursor) — enough for the target scale; WebSocket push is a later optimisation."""
from __future__ import annotations

import re
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..models import ChatMessage, ChatRead, ChatReport, GuildMember, PlayerProfile, Sanction
from . import progression as P
from .common import card, cfg

router = APIRouter(prefix="/chat", tags=["chat"])


def C() -> dict:
    return cfg()["chat"]


# ------------------------------------------------------------------ filter
_LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(ru|com|net|org|xyz|io|рф)\b|t\.me/|@\w{4,})", re.I)
_PHONE = re.compile(r"(\+?\d[\d\-\s()]{8,}\d)")
_REPEAT = re.compile(r"(.)\1{5,}")
_LEET = str.maketrans({"0": "о", "3": "з", "4": "ч", "6": "б", "@": "а", "a": "а", "e": "е", "o": "о", "p": "р",
                       "c": "с", "x": "х", "y": "у", "k": "к", "m": "м", "t": "т", "b": "в", "h": "н"})


def _norm(text: str) -> str:
    t = text.lower().translate(_LEET)
    return re.sub(r"[\s\.\-_*]+", "", t)


def _bad_word(word: str) -> bool:
    w = _norm(word)
    for b in C()["bad_words"]:
        # short roots only at the start of a word ("плохо" is fine), longer ones anywhere inside it
        if (len(b) <= 4 and w.startswith(b)) or (len(b) > 4 and b in w):
            return True
    return False


def contains_bad(text: str) -> bool:
    words = re.findall(r"[\w*@.\-]+", text.lower())
    if any(_bad_word(w) for w in words):
        return True
    # spaced-out evasion ("д у р а к"): join runs of single letters
    singles = "".join(w for w in re.findall(r"\b\w\b", text.lower()))
    return len(singles) >= 3 and any(b in _norm(singles) for b in C()["bad_words"])


def clean(text: str) -> tuple[str, bool]:
    """Masks profanity, links and phone numbers. Returns (text, was_filtered)."""
    t = " ".join(text.strip().split())
    filtered = False
    words = t.split(" ")
    for i, w in enumerate(words):
        if _bad_word(w):
            words[i] = "***"
            filtered = True
    t = " ".join(words)
    if contains_bad(t):  # spaced-out letters left after the per-word pass
        t = re.sub(r"(?:\b\w\b\s*){3,}", "*** ", t).strip()
        filtered = True
    for rx in (_LINK, _PHONE):
        if rx.search(t):
            t = rx.sub("[скрыто]", t)
            filtered = True
    t = _REPEAT.sub(lambda m: m.group(1) * 3, t)
    return t, filtered


def meaningful(text: str) -> bool:
    words = [w for w in re.findall(r"[\wёЁ]+", text.lower()) if len(w) > 1]
    return len(text) >= cfg()["progression"]["chat_meaningful_min_len"] and \
        len(set(words)) >= cfg()["progression"]["chat_meaningful_min_unique_words"]


# ------------------------------------------------------------------ channels & access
def dm_channel(a: str, b: str) -> str:
    x, y = sorted([a, b])
    return f"dm:{x}:{y}"


def can_read(db: Session, user_id: str, channel: str) -> bool:
    if channel == "global":
        return True
    if channel.startswith("guild:"):
        m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
        return m is not None and channel == f"guild:{m.guild_id}"
    if channel.startswith("dm:"):
        return user_id in channel.split(":")[1:]
    from .channels import can_read as extra_can_read
    return extra_can_read(db, user_id, channel)  # region / event / alliance / group / news (Living World AI stage 8)


def active_sanction(db: Session, user_id: str, kinds: tuple[str, ...]) -> Sanction | None:
    now = utcnow()
    for s in db.scalars(select(Sanction).where(Sanction.user_id == user_id, Sanction.status == "active",
                                               Sanction.kind.in_(kinds))):
        if s.ends_at is None or as_utc(s.ends_at) > now:
            return s
        s.status = "expired"
    return None


_recent: dict[str, deque] = {}


def flood_check(user_id: str) -> None:
    now = time.monotonic()
    q = _recent.setdefault(user_id, deque(maxlen=20))
    if q and now - q[-1] < C()["min_interval_s"]:
        raise GameError("too_fast", "Не так быстро: подождите пару секунд", 429)
    burst = [t for t in q if now - t < C()["burst_window_s"]]
    if len(burst) >= C()["burst"]:
        raise GameError("flood", "Слишком много сообщений подряд, передохните", 429)
    q.append(now)


def post(db: Session, user_id: str | None, channel: str, text: str, is_ai: bool = False) -> ChatMessage:
    text, filtered = clean(text[: C()["max_len"]])
    if not text:
        raise GameError("empty", "Пустое сообщение")
    if user_id:
        since = utcnow() - timedelta(seconds=C()["duplicate_window_s"])
        dup = db.scalar(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.text == text,
                                                  ChatMessage.created_at >= since))
        if dup is not None:
            raise GameError("duplicate", "Такое сообщение уже отправлено", 409)
    msg = ChatMessage(channel=channel, user_id=user_id, text=text, is_ai=is_ai, filtered=filtered, reactions={})
    db.add(msg)
    db.flush()
    if user_id and not is_ai and not filtered and meaningful(text):
        P.on(db, user_id, "chat_meaningful", ref=str(msg.id))
    return msg


def system_message(db: Session, channel: str, text: str) -> None:
    db.add(ChatMessage(channel=channel, user_id=None, text=text[:400], reactions={}))


def _avatar_hero(db: Session, user_id: str) -> str:
    """Portrait for the chat avatar: the hero in the first filled formation slot."""
    from ..models import Formation, PlayerHero
    f = db.scalar(select(Formation).where(Formation.user_id == user_id, Formation.kind == "campaign"))
    for pid in (f.slots if f else []):
        if pid:
            ph = db.get(PlayerHero, pid)
            if ph:
                return ph.hero_code
    return "azamat"


def prune(db: Session) -> int:
    """Drops old lines from public chats (global, guild, region, events) once a channel
    has more than keep_per_channel messages. Private messages stay. AI memory lives in
    its own tables and is not touched here."""
    keep = int(C().get("keep_per_channel", 50))
    reported = set(db.scalars(select(ChatReport.message_id).where(ChatReport.status == "open", ChatReport.message_id.is_not(None))))
    removed = 0
    for (ch,) in db.execute(select(ChatMessage.channel).group_by(ChatMessage.channel)
                            .having(func.count() > keep)).all():
        if str(ch).startswith("dm:"):
            continue
        border = db.scalar(select(ChatMessage.id).where(ChatMessage.channel == ch).order_by(ChatMessage.id.desc())
                           .offset(keep - 1).limit(1))
        if border is None:
            continue
        q = db.query(ChatMessage).filter(ChatMessage.channel == ch, ChatMessage.id < border)
        if reported:
            q = q.filter(ChatMessage.id.notin_(reported))
        removed += q.delete(synchronize_session=False)
    db.flush()
    return removed


def view(db: Session, m: ChatMessage, viewer: str, cards: dict) -> dict:
    a = None
    if m.user_id:
        if m.user_id not in cards:
            p = db.get(PlayerProfile, m.user_id)
            gm = db.scalar(select(GuildMember).where(GuildMember.user_id == m.user_id))
            from ..models import Guild
            g = db.get(Guild, gm.guild_id) if gm else None
            cards[m.user_id] = {"user_id": m.user_id, "nickname": p.nickname if p else "?", "is_ai": bool(p and p.is_ai),
                                "level": p.level if p else 1, "avatar": p.avatar if p else "",
                                "avatar_hero": _avatar_hero(db, m.user_id),
                                "guild_tag": g.tag if g else "", "guild_name": g.name if g else "",
                                "frame": (p.cosmetics or {}).get("frame") if p else None}
        a = cards[m.user_id]
    return {"id": m.id, "channel": m.channel, "author": a, "system": m.user_id is None, "text": m.text,
            "is_ai": m.is_ai, "at": as_utc(m.created_at).isoformat(), "mine": m.user_id == viewer,
            "reactions": {k: {"count": len(v), "mine": viewer in v} for k, v in (m.reactions or {}).items() if v}}


# ------------------------------------------------------------------ API
@router.get("/channels")
def channels(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    chans = [{"channel": "global", "name": "Общий чат"}]
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == user.id))
    if m:
        chans.append({"channel": f"guild:{m.guild_id}", "name": "Гильдия"})
    dms = db.execute(select(ChatMessage.channel, func.max(ChatMessage.id)).where(
        ChatMessage.channel.like(f"dm:%{user.id}%")).group_by(ChatMessage.channel)
        .order_by(func.max(ChatMessage.id).desc()).limit(30)).all()
    for ch, _ in dms:
        other = [x for x in ch.split(":")[1:] if x != user.id]
        if other:
            c = card(db, other[0], user.id)
            chans.append({"channel": ch, "name": c["nickname"], "is_ai": c["is_ai"], "user_id": other[0]})
    from .channels import extra_channels
    chans.extend(extra_channels(db, user.id))
    for c in chans:
        r = db.get(ChatRead, (user.id, c["channel"]))
        last = r.last_id if r else 0
        c["unread"] = db.scalar(select(func.count()).select_from(ChatMessage).where(
            ChatMessage.channel == c["channel"], ChatMessage.id > last, ChatMessage.hidden.is_(False),
            or_(ChatMessage.user_id.is_(None), ChatMessage.user_id != user.id))) or 0
    mute = active_sanction(db, user.id, ("mute", "temp_ban", "perm_ban"))
    db.commit()
    return {"channels": chans, "reactions": C()["reactions"],
            "muted_until": (as_utc(mute.ends_at).isoformat() if mute and mute.ends_at else ("forever" if mute else None))}


@router.get("/messages")
def messages(channel: str = Query(max_length=80), after: int = Query(0, ge=0), before: int = Query(0, ge=0),
             user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if not can_read(db, user.id, channel):
        raise GameError("forbidden", "Нет доступа к каналу", 403)
    from .common import blocked_ids
    hide = blocked_ids(db, user.id)
    stmt = select(ChatMessage).where(ChatMessage.channel == channel, ChatMessage.hidden.is_(False))
    if after:
        stmt = stmt.where(ChatMessage.id > after).order_by(ChatMessage.id).limit(C()["page"])
        rows = list(db.scalars(stmt))
    else:
        if before:
            stmt = stmt.where(ChatMessage.id < before)
        rows = list(reversed(db.scalars(stmt.order_by(ChatMessage.id.desc()).limit(C()["page"])).all()))
    from .ai.control import player_prefs
    hide_ai = (channel == "global" or channel.startswith(("region:", "event:"))) and \
        not player_prefs(db.get(PlayerProfile, user.id)).get("show_ai_chat", True)
    rows = [m for m in rows if m.user_id not in hide and not (hide_ai and m.is_ai)]
    cards: dict = {}
    out = [view(db, m, user.id, cards) for m in rows]
    if out:
        r = db.get(ChatRead, (user.id, channel))
        top = max(m["id"] for m in out)
        if r is None:
            db.add(ChatRead(user_id=user.id, channel=channel, last_id=top))
        elif top > r.last_id:
            r.last_id = top
        db.commit()
    return {"messages": out, "channel": channel}


class SendIn(BaseModel):
    channel: str | None = Field(default=None, max_length=80)
    to_user: str | None = Field(default=None, max_length=36)
    text: str = Field(min_length=1, max_length=400)


@router.post("/send")
def send(body: SendIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    s = active_sanction(db, user.id, ("mute", "temp_ban", "perm_ban"))
    if s:
        until = as_utc(s.ends_at).strftime("%d.%m %H:%M UTC") if s.ends_at else "бессрочно"
        db.commit()
        raise GameError("muted", f"Чат ограничен до {until}: {s.reason}", 403)
    channel = body.channel
    if body.to_user:
        from .friends import blocked
        if blocked(db, user.id, body.to_user):
            raise GameError("blocked", "Игрок недоступен", 403)
        if db.get(PlayerProfile, body.to_user) is None:
            raise GameError("not_found", "Игрок не найден", 404)
        channel = dm_channel(user.id, body.to_user)
    if not channel or not can_read(db, user.id, channel):
        raise GameError("forbidden", "Нет доступа к каналу", 403)
    if channel == "news":
        raise GameError("read_only", "В канал «Объявления» пишет только администрация", 403)
    flood_check(user.id)
    msg = post(db, user.id, channel, body.text)
    db.commit()
    if channel.startswith("dm:"):
        other = [x for x in channel.split(":")[1:] if x != user.id]
        if other and db.get(PlayerProfile, other[0]) and db.get(PlayerProfile, other[0]).is_ai:
            from .ai.control import dm_allowed
            me = db.get(PlayerProfile, user.id)
            if dm_allowed(me):  # decision D-C1: AI do not write privately to minors / unknown age (no replies either)
                from ..ai.outreach import player_replied
                from .ai.population import queue_reply
                player_replied(db, user.id, msg.text)
                queue_reply(db, other[0], user.id, channel, msg.text)
                db.commit()
    elif channel == "global" or channel.startswith(("guild:", "region:", "event:", "alliance:", "group:")):
        from .ai.population import queue_mention
        queue_mention(db, channel, user.id, msg.text)
        db.commit()
    return {"message": view(db, msg, user.id, {})}


class ReactIn(BaseModel):
    emoji: str = Field(max_length=8)


@router.post("/messages/{msg_id}/react")
def react(msg_id: int, body: ReactIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if body.emoji not in C()["reactions"]:
        raise GameError("bad_emoji", "Такой реакции нет")
    m = db.get(ChatMessage, msg_id, with_for_update=True)
    if m is None or not can_read(db, user.id, m.channel):
        raise GameError("not_found", "Сообщение не найдено", 404)
    r = {k: list(v) for k, v in (m.reactions or {}).items()}
    lst = r.setdefault(body.emoji, [])
    if user.id in lst:
        lst.remove(user.id)
    else:
        lst.append(user.id)
    m.reactions = r
    db.commit()
    return {"reactions": {k: {"count": len(v), "mine": user.id in v} for k, v in r.items() if v}}


class ReportIn(BaseModel):
    message_id: int | None = None
    user_id: str | None = Field(default=None, max_length=36)
    reason: str = Field(pattern="^(abuse|spam|cheat|scam|nickname|other)$")
    comment: str = Field(default="", max_length=300)


@router.post("/report")
def report(body: ReportIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    target = body.user_id
    if body.message_id:
        m = db.get(ChatMessage, body.message_id)
        if m is None or not can_read(db, user.id, m.channel) or m.user_id is None:
            raise GameError("not_found", "Сообщение не найдено", 404)
        target = m.user_id
    if not target or target == user.id or db.get(PlayerProfile, target) is None:
        raise GameError("bad_request", "Неверная цель жалобы")
    if db.scalar(select(ChatReport).where(ChatReport.reporter_id == user.id, ChatReport.target_id == target,
                                          ChatReport.message_id == body.message_id)):
        return {"ok": True, "duplicate": True}
    db.add(ChatReport(message_id=body.message_id, target_id=target, reporter_id=user.id, reason=body.reason,
                      comment=body.comment))
    db.flush()
    from .moderation import auto_review
    auto_review(db, target)
    db.commit()
    return {"ok": True}


@router.get("/unread")
def unread(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    total = 0
    for ch in ["global"] + ([f"guild:{m.guild_id}"] if (m := db.scalar(select(GuildMember).where(GuildMember.user_id == user.id))) else []):
        r = db.get(ChatRead, (user.id, ch))
        total += db.scalar(select(func.count()).select_from(ChatMessage).where(
            ChatMessage.channel == ch, ChatMessage.id > (r.last_id if r else 0),
            or_(ChatMessage.user_id.is_(None), ChatMessage.user_id != user.id))) or 0
    return {"unread": min(total, 99)}
