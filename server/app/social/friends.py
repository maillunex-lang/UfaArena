"""Friends, presence, recommendations, invite links, gifts, help and friend profiles."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.db import get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..models import (
    Achievement, ArenaMatch, FortressBuilding, Friendship, FriendGift, FriendInvite, FriendRequest, GuildMember,
    PlayerHero, PlayerProfile, RaidAttack, StatCounter, UserBlock, WalletTransaction,
)
from ..services import spend
from . import progression as P
from .common import by_public_id, card, cfg, day, freeze_squad, give, profile, squad_power, week_key

router = APIRouter(prefix="/social", tags=["social"])


def F() -> dict:
    return cfg()["friends"]


# ------------------------------------------------------------------ helpers
def are_friends(db: Session, a: str, b: str) -> bool:
    return db.get(Friendship, (a, b)) is not None


def friend_ids(db: Session, user_id: str) -> list[str]:
    return list(db.scalars(select(Friendship.friend_id).where(Friendship.user_id == user_id)))


def blocked(db: Session, a: str, b: str) -> bool:
    return db.get(UserBlock, (a, b)) is not None or db.get(UserBlock, (b, a)) is not None


def make_friends(db: Session, a: str, b: str, source: str) -> None:
    for x, y in ((a, b), (b, a)):
        if db.get(Friendship, (x, y)) is None:
            db.add(Friendship(user_id=x, friend_id=y, source=source))
    db.flush()
    for x in (a, b):
        P.add_stat(db, x, "friends", absolute=len(friend_ids(db, x)))


def request_friend(db: Session, me: str, target: str, source: str) -> dict:
    if me == target:
        raise GameError("self", "Нельзя добавить себя")
    if are_friends(db, me, target):
        raise GameError("already_friends", "Вы уже друзья", 409)
    if blocked(db, me, target):
        raise GameError("blocked", "Игрок недоступен", 403)
    lim = F()["max_friends"]
    if len(friend_ids(db, me)) >= lim:
        raise GameError("friends_full", f"У вас уже {lim} друзей — это максимум", 409)
    if len(friend_ids(db, target)) >= lim:
        raise GameError("target_full", "У игрока максимум друзей", 409)
    # a reverse pending request means mutual intent: accept immediately
    rev = db.scalar(select(FriendRequest).where(FriendRequest.from_id == target, FriendRequest.to_id == me,
                                                FriendRequest.status == "pending"))
    if rev is not None:
        rev.status = "accepted"
        make_friends(db, me, target, source)
        return {"status": "friends"}
    if db.scalar(select(FriendRequest).where(FriendRequest.from_id == me, FriendRequest.to_id == target,
                                             FriendRequest.status == "pending")):
        return {"status": "pending"}
    out_cnt = db.scalar(select(func.count()).select_from(FriendRequest).where(
        FriendRequest.from_id == me, FriendRequest.status == "pending")) or 0
    if out_cnt >= F()["max_pending_out"]:
        raise GameError("too_many_requests", "Слишком много неотвеченных заявок", 429)
    req = FriendRequest(from_id=me, to_id=target, source=source)
    db.add(req)
    db.flush()
    tp = db.get(PlayerProfile, target)
    if tp is not None and tp.is_ai:
        from .ai.population import ai_consider_friend
        if ai_consider_friend(db, target, me):
            req.status = "accepted"
            make_friends(db, me, target, source)
            return {"status": "friends", "ai": True}
    return {"status": "pending", "request_id": req.id}


def _midnight():
    n = utcnow()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def blessing_left(db: Session, user_id: str) -> int:
    sc = db.get(StatCounter, (user_id, "blessing_battles"))
    return sc.value if sc else 0


def consume_blessing(db: Session, user_id: str) -> float:
    """Friend help: +atk% for the next N PvE battles. Returns bonus to apply to this battle."""
    sc = db.get(StatCounter, (user_id, "blessing_battles"))
    if sc is None or sc.value <= 0:
        return 0.0
    sc.value -= 1
    return float(F()["help_blessing"]["atk_pct"])


# ------------------------------------------------------------------ list & search
@router.get("/friends")
def friends(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    d = day()
    sent_today = set(db.scalars(select(FriendGift.to_id).where(FriendGift.from_id == user.id, FriendGift.day == d,
                                                               FriendGift.kind == "gift")))
    helped_today = set(db.scalars(select(FriendGift.to_id).where(FriendGift.from_id == user.id, FriendGift.day == d,
                                                                 FriendGift.kind == "help")))
    items = []
    for fid in friend_ids(db, user.id):
        c = card(db, fid, user.id)
        c["gift_sent"] = fid in sent_today
        c["helped"] = fid in helped_today
        items.append(c)
    order = {"online": 0, "recent": 1, "hidden": 2, "offline": 3}
    items.sort(key=lambda c: (order.get(c["presence"], 3), -c["power"]))
    inc = [{"id": r.id, "source": r.source, "from": card(db, r.from_id, user.id)} for r in db.scalars(
        select(FriendRequest).where(FriendRequest.to_id == user.id, FriendRequest.status == "pending")
        .order_by(FriendRequest.created_at.desc()).limit(50))]
    out = [{"id": r.id, "to": card(db, r.to_id, user.id)} for r in db.scalars(
        select(FriendRequest).where(FriendRequest.from_id == user.id, FriendRequest.status == "pending").limit(50))]
    gifts_waiting = db.scalar(select(func.count()).select_from(FriendGift).where(
        FriendGift.to_id == user.id, FriendGift.claimed_at.is_(None))) or 0
    me = profile(db, user.id)
    return {"friends": items, "max": F()["max_friends"], "incoming": inc, "outgoing": out,
            "gifts_waiting": gifts_waiting, "presence_hidden": bool(me.presence_hidden),
            "limits": {"gift_send_per_day": F()["gift_send_per_day"], "help_per_day": F()["help_per_day"],
                       "sent_today": len(sent_today), "helped_today": len(helped_today)},
            "blessing_battles": blessing_left(db, user.id)}


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=32), offset: int = Query(0, ge=0, le=500),
           user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    q = q.strip()
    stmt = select(PlayerProfile).where(PlayerProfile.user_id != user.id)
    if q.upper().startswith("UR-"):
        stmt = stmt.where(PlayerProfile.uralia_id == q.upper())
    else:
        like = q.replace("%", "").replace("_", "") + "%"
        stmt = stmt.where(PlayerProfile.nickname.ilike(like))
    rows = db.scalars(stmt.order_by(PlayerProfile.level.desc()).offset(offset).limit(20)).all()
    return {"items": [card(db, p.user_id, user.id) for p in rows], "offset": offset, "next": offset + 20 if len(rows) == 20 else None}


@router.get("/recommendations")
def recommendations(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Similar level/power, guildmates, recent co-activity (raids, arena). AI personas are labelled."""
    me = profile(db, user.id)
    exclude = set(friend_ids(db, user.id)) | {user.id}
    exclude |= set(db.scalars(select(UserBlock.blocked_id).where(UserBlock.user_id == user.id)))
    exclude |= set(db.scalars(select(FriendRequest.to_id).where(FriendRequest.from_id == user.id,
                                                                FriendRequest.status == "pending")))
    picks: dict[str, str] = {}
    gm = db.scalar(select(GuildMember).where(GuildMember.user_id == user.id))
    if gm:
        for uid in db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == gm.guild_id)):
            if uid not in exclude:
                picks.setdefault(uid, "guild")
    since = utcnow() - timedelta(days=7)
    for m in db.scalars(select(ArenaMatch).where(ArenaMatch.attacker_id == user.id, ArenaMatch.created_at >= since)
                        .order_by(ArenaMatch.created_at.desc()).limit(20)):
        if m.defender_id not in exclude:
            picks.setdefault(m.defender_id, "activity")
    for p in db.scalars(select(PlayerProfile).where(
            PlayerProfile.user_id.notin_(exclude), PlayerProfile.is_ai.is_(False),
            PlayerProfile.level.between(max(1, me.level - 5), me.level + 5))
            .order_by(PlayerProfile.last_seen_at.desc().nullslast()).limit(14)):
        picks.setdefault(p.user_id, "level")
    # a few labelled AI residents of similar level so a new world never looks empty
    for p in db.scalars(select(PlayerProfile).where(PlayerProfile.user_id.notin_(exclude), PlayerProfile.is_ai.is_(True))
                        .order_by(func.abs(PlayerProfile.level - me.level)).limit(6)):
        picks.setdefault(p.user_id, "ai")
    reason = {"guild": "Из вашей гильдии", "activity": "Встречались в боях", "level": "Близкий уровень",
              "ai": "Житель Уралии"}
    items = []
    for uid, why in list(picks.items())[:20]:
        c = card(db, uid, user.id)
        c["reason"] = reason[why]
        items.append(c)
    return {"items": items}


# ------------------------------------------------------------------ requests
class RequestIn(BaseModel):
    uralia_id: str | None = Field(default=None, max_length=16)
    user_id: str | None = Field(default=None, max_length=36)
    nickname: str | None = Field(default=None, max_length=32)
    source: str = Field(default="id", pattern="^(id|name|recommend|activity|guild|invite)$")


@router.post("/friends/request")
def friend_request(body: RequestIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if body.uralia_id:
        target = by_public_id(db, body.uralia_id).user_id
    elif body.user_id:
        target = profile(db, body.user_id).user_id
    elif body.nickname:
        rows = db.scalars(select(PlayerProfile).where(PlayerProfile.nickname == body.nickname.strip()).limit(2)).all()
        if not rows:
            raise GameError("not_found", "Игрок с таким именем не найден", 404)
        if len(rows) > 1:
            raise GameError("ambiguous", "Несколько игроков с таким именем — используйте ID", 409)
        target = rows[0].user_id
    else:
        raise GameError("bad_request", "Укажите ID или имя игрока")
    res = request_friend(db, user.id, target, body.source)
    audit(db, user.id, "social.friend_request", target=target, status=res["status"])
    db.commit()
    return res


@router.post("/friends/requests/{req_id}/{action}")
def friend_respond(req_id: str, action: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    r = db.get(FriendRequest, req_id, with_for_update=True)
    if r is None or r.status != "pending" or (r.to_id != user.id and not (action == "cancel" and r.from_id == user.id)):
        raise GameError("not_found", "Заявка не найдена", 404)
    if action == "accept":
        lim = F()["max_friends"]
        if len(friend_ids(db, user.id)) >= lim or len(friend_ids(db, r.from_id)) >= lim:
            raise GameError("friends_full", "Достигнут лимит друзей", 409)
        r.status = "accepted"
        make_friends(db, user.id, r.from_id, r.source)
    elif action in ("decline", "cancel"):
        r.status = "declined" if action == "decline" else "cancelled"
    else:
        raise GameError("bad_request", "Неизвестное действие")
    db.commit()
    return {"status": r.status}


@router.post("/friends/{friend_id}/remove")
def friend_remove(friend_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    for x, y in ((user.id, friend_id), (friend_id, user.id)):
        f = db.get(Friendship, (x, y))
        if f:
            db.delete(f)
    db.flush()
    P.add_stat(db, user.id, "friends", absolute=len(friend_ids(db, user.id)))
    db.commit()
    return {"ok": True}


@router.post("/block/{target_id}")
def block(target_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    profile(db, target_id)
    if db.get(UserBlock, (user.id, target_id)) is None:
        db.add(UserBlock(user_id=user.id, blocked_id=target_id))
    for x, y in ((user.id, target_id), (target_id, user.id)):
        f = db.get(Friendship, (x, y))
        if f:
            db.delete(f)
    db.commit()
    return {"ok": True}


@router.post("/unblock/{target_id}")
def unblock(target_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    b = db.get(UserBlock, (user.id, target_id))
    if b:
        db.delete(b)
        db.commit()
    return {"ok": True}


class PresenceIn(BaseModel):
    hidden: bool


@router.post("/presence")
def set_presence(body: PresenceIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = profile(db, user.id)
    p.presence_hidden = body.hidden
    db.commit()
    return {"presence_hidden": p.presence_hidden}


# ------------------------------------------------------------------ invite links
@router.post("/invite")
def invite(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    inv = db.scalar(select(FriendInvite).where(FriendInvite.user_id == user.id))
    if inv is None:
        inv = FriendInvite(code="F" + secrets.token_hex(4).upper(), user_id=user.id)
        db.add(inv)
        db.commit()
    return {"code": inv.code, "uses": inv.uses, "link": f"uralia://friend/{inv.code}"}


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


@router.post("/invite/redeem")
def invite_redeem(body: RedeemIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    inv = db.get(FriendInvite, body.code.strip().upper())
    if inv is None:
        raise GameError("not_found", "Приглашение не найдено", 404)
    if inv.user_id == user.id:
        raise GameError("self", "Это ваше приглашение")
    if not are_friends(db, user.id, inv.user_id):
        lim = F()["max_friends"]
        if len(friend_ids(db, user.id)) >= lim or len(friend_ids(db, inv.user_id)) >= lim:
            raise GameError("friends_full", "Достигнут лимит друзей", 409)
        make_friends(db, user.id, inv.user_id, "invite")
        inv.uses += 1
    db.commit()
    return {"status": "friends", "friend": card(db, inv.user_id, user.id)}


# ------------------------------------------------------------------ gifts & help
def _send(db: Session, me: str, to: str, kind: str) -> FriendGift:
    if not are_friends(db, me, to):
        raise GameError("not_friends", "Подарки можно отправлять только друзьям", 403)
    d = day()
    lim = F()["gift_send_per_day"] if kind == "gift" else F()["help_per_day"]
    sent = db.scalar(select(func.count()).select_from(FriendGift).where(
        FriendGift.from_id == me, FriendGift.day == d, FriendGift.kind == kind)) or 0
    if sent >= lim:
        raise GameError("limit", "Дневной лимит исчерпан", 429)
    if db.scalar(select(FriendGift).where(FriendGift.from_id == me, FriendGift.to_id == to, FriendGift.day == d,
                                          FriendGift.kind == kind)):
        raise GameError("already_sent", "Сегодня уже отправлено этому другу", 409)
    contents = dict(F()["gift_contents"] if kind == "gift" else F()["help_contents"])
    g = FriendGift(from_id=me, to_id=to, day=d, kind=kind, contents=contents)
    db.add(g)
    db.flush()
    P.on(db, me, "gift_sent" if kind == "gift" else "help", ref=to)
    return g


@router.post("/gifts/send/{friend_id}")
def gift_send(friend_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
              db: Session = Depends(get_db)):
    def do():
        _send(db, user.id, friend_id, "gift")
        return {"ok": True}
    return run_idempotent(db, user.id, key, f"gift:{friend_id}", {}, do)


@router.post("/gifts/send-all")
def gift_send_all(user: CurrentUser = Depends(player), key: str = Depends(require_key), db: Session = Depends(get_db)):
    def do():
        n = 0
        d = day()
        done = set(db.scalars(select(FriendGift.to_id).where(FriendGift.from_id == user.id, FriendGift.day == d,
                                                             FriendGift.kind == "gift")))
        for fid in friend_ids(db, user.id):
            if fid in done or n + len(done) >= F()["gift_send_per_day"]:
                continue
            _send(db, user.id, fid, "gift")
            n += 1
        return {"sent": n}
    return run_idempotent(db, user.id, key, "gift:all", {}, do)


@router.post("/help/{friend_id}")
def help_friend(friend_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
                db: Session = Depends(get_db)):
    """Help a friend: herbs + "Благословение друга" (+atk% for their next PvE battles)."""
    def do():
        _send(db, user.id, friend_id, "help")
        return {"ok": True}
    return run_idempotent(db, user.id, key, f"help:{friend_id}", {}, do)


@router.get("/gifts")
def gifts(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    rows = db.scalars(select(FriendGift).where(FriendGift.to_id == user.id).order_by(FriendGift.created_at.desc()).limit(60))
    d = day()
    claimed_today = db.scalar(select(func.count()).select_from(FriendGift).where(
        FriendGift.to_id == user.id, FriendGift.claimed_at >= _midnight())) or 0
    return {"items": [{"id": g.id, "kind": g.kind, "from": card(db, g.from_id, user.id)["nickname"],
                       "from_ai": card(db, g.from_id)["is_ai"], "contents": g.contents, "day": g.day,
                       "claimed": g.claimed_at is not None} for g in rows],
            "claim_limit": F()["gift_claim_per_day"], "claimed_today": claimed_today}


@router.post("/gifts/claim-all")
def gifts_claim(user: CurrentUser = Depends(player), key: str = Depends(require_key), db: Session = Depends(get_db)):
    def do():
        d = day()
        claimed_today = db.scalar(select(func.count()).select_from(FriendGift).where(
            FriendGift.to_id == user.id, FriendGift.claimed_at >= _midnight())) or 0
        room = max(0, F()["gift_claim_per_day"] - claimed_today)
        total: dict[str, int] = {}
        blessings = 0
        rows = db.scalars(select(FriendGift).where(FriendGift.to_id == user.id, FriendGift.claimed_at.is_(None))
                          .order_by(FriendGift.created_at).limit(room).with_for_update()).all()
        for g in rows:
            g.claimed_at = utcnow()
            for k, v in g.contents.items():
                total[k] = total.get(k, 0) + int(v)
            if g.kind == "help":
                blessings += int(F()["help_blessing"]["battles"])
        if total:
            give(db, user.id, total, "friend_gift")
        if blessings:
            sc = db.get(StatCounter, (user.id, "blessing_battles"))
            if sc is None:
                sc = StatCounter(user_id=user.id, key="blessing_battles", value=0)
                db.add(sc)
            sc.value = min(15, (sc.value or 0) + blessings)
        return {"claimed": len(rows), "rewards": total, "blessing_battles": blessing_left(db, user.id) + 0}
    return run_idempotent(db, user.id, key, "gift:claim", {}, do)


# ------------------------------------------------------------------ friendship token shop
@router.get("/token-shop")
def token_shop(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    wk = week_key()
    items = []
    for it in F()["token_shop"]:
        sc = db.get(StatCounter, (user.id, f"t:{it['id']}:{wk}"))
        items.append({**it, "bought": sc.value if sc else 0})
    return {"items": items, "week": wk}


@router.post("/token-shop/{item_id}/buy")
def token_buy(item_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
              db: Session = Depends(get_db)):
    it = next((x for x in F()["token_shop"] if x["id"] == item_id), None)
    if it is None:
        raise GameError("not_found", "Товар не найден", 404)

    def do():
        k = f"t:{it['id']}:{week_key()}"
        sc = db.get(StatCounter, (user.id, k), with_for_update=True)
        if sc is None:
            sc = StatCounter(user_id=user.id, key=k, value=0)
            db.add(sc)
        if sc.value >= it["weekly_limit"]:
            raise GameError("limit", "Недельный лимит исчерпан", 409)
        spend(db, user.id, {"friend_tokens": it["cost"]}, "token_shop", it["id"])
        sc.value += 1
        give(db, user.id, it["contents"], "token_shop", it["id"])
        from ..services import wallet_dict
        return {"ok": True, "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, f"token:{item_id}", {}, do)


# ------------------------------------------------------------------ friend profile
@router.get("/profile/{target_id}")
def friend_profile(target_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    c = card(db, target_id, user.id)
    if blocked(db, user.id, target_id):
        raise GameError("blocked", "Профиль недоступен", 403)
    heroes = [{"hero_code": ph.hero_code, "name": ph.hero.name, "level": ph.level, "stars": ph.stars,
               "rarity": ph.hero.rarity, "faction": ph.hero.faction_code, "class": ph.hero.class_code}
              for ph in db.scalars(select(PlayerHero).where(PlayerHero.user_id == target_id))]
    heroes.sort(key=lambda h: (-h["rarity"], -h["level"]))
    try:
        squad = freeze_squad(db, target_id)
    except GameError:
        squad = []
    activity = []
    for m in db.scalars(select(ArenaMatch).where(or_(ArenaMatch.attacker_id == target_id, ArenaMatch.defender_id == target_id))
                        .order_by(ArenaMatch.created_at.desc()).limit(8)):
        won = (m.result == "victory") == (m.attacker_id == target_id)
        activity.append({"at": m.created_at.isoformat(), "kind": "arena", "match_id": m.id,
                         "text": ("Победа" if won else "Поражение") + (" в атаке на арене" if m.attacker_id == target_id else " в защите на арене")})
    for a in db.scalars(select(RaidAttack).where(RaidAttack.user_id == target_id).order_by(RaidAttack.created_at.desc()).limit(5)):
        activity.append({"at": a.created_at.isoformat(), "kind": "raid", "text": f"Нанёс боссу {a.damage:,} урона".replace(",", " ")})
    cfg_ach = cfg()["progression"]["achievements"]
    for a in db.scalars(select(Achievement).where(Achievement.user_id == target_id).order_by(Achievement.achieved_at.desc()).limit(5)):
        if a.code in cfg_ach:
            activity.append({"at": a.achieved_at.isoformat(), "kind": "achievement", "text": "Достижение: " + cfg_ach[a.code]["name"]})
    activity.sort(key=lambda x: x["at"], reverse=True)
    fortress = {b.code: b.level for b in db.scalars(select(FortressBuilding).where(FortressBuilding.user_id == target_id))}
    return {"card": c, "friend": are_friends(db, user.id, target_id), "heroes": heroes, "squad": squad,
            "squad_power": squad_power(squad), "activity": activity[:15], "fortress": fortress,
            "stats": P.stats(db, target_id) if c["is_ai"] or are_friends(db, user.id, target_id) or target_id == user.id else {},
            "achievements": db.scalar(select(func.count()).select_from(Achievement).where(Achievement.user_id == target_id)) or 0}


_ = WalletTransaction  # ledger is the source of truth for every gift/claim above
