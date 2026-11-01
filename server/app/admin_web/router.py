"""Web admin panel API (/admin/api/web/*): server settings, APK releases, game events, mail to everyone,
admin chat, replaceable art. Same X-Admin-Token as the rest of the admin API; every write is logged."""
from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import as_utc, get_db, utcnow
from ..core.errors import GameError
from ..models import (
    AdminAction, ChatMessage, Guild, MailMessage, PlayerMail, PlayerProfile, RaidInstance, ServerSetting, Tournament,
    WorldEvent,
)
from ..modules.admin import admin
from . import art

router = APIRouter(prefix="/admin/api/web", tags=["admin-web"])
page = APIRouter(tags=["admin-web"])


@page.get("/admin", response_class=HTMLResponse)
def admin_page():
    from pathlib import Path
    return HTMLResponse((Path(__file__).resolve().parent / "admin.html").read_text(encoding="utf-8"))


def _log(db: Session, who: str, action: str, **details) -> None:
    db.add(AdminAction(admin=who, action=action, details=details))


# ------------------------------------------------------------------ overview
@router.get("/overview")
def overview(who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..social import scheduler
    now = utcnow()
    cnt = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(*w)) or 0  # noqa: E731
    real = PlayerProfile.is_ai.is_(False)
    return {
        "players": cnt(PlayerProfile, real),
        "online": cnt(PlayerProfile, real, PlayerProfile.last_seen_at >= now - timedelta(minutes=3)),
        "active_day": cnt(PlayerProfile, real, PlayerProfile.last_seen_at >= now - timedelta(days=1)),
        "ai": cnt(PlayerProfile, PlayerProfile.is_ai.is_(True)),
        "guilds": cnt(Guild, Guild.is_ai.is_(False)), "ai_guilds": cnt(Guild, Guild.is_ai.is_(True)),
        "chat_hour": cnt(ChatMessage, ChatMessage.created_at >= now - timedelta(hours=1)),
        "events": [{"id": e.id, "name": e.name, "progress": e.progress, "goal": e.goal, "ends_at": as_utc(e.ends_at).isoformat()}
                   for e in db.scalars(select(WorldEvent).where(WorldEvent.status == "active"))],
        "jobs": scheduler.status(),
    }


# ------------------------------------------------------------------ release / APK
class ReleaseIn(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    min_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(default="", max_length=120)
    notes: list[str] = Field(default_factory=list, max_length=20)
    url: str | None = Field(default=None, max_length=300)
    file: str | None = Field(default=None, max_length=80)


@router.get("/release")
def release_get(who: str = Depends(admin)):
    from ..modules.release import release
    d = get_settings().downloads_path
    apks = sorted([{"name": f.name, "size": f.stat().st_size} for f in d.glob("*.apk")], key=lambda x: x["name"]) if d.exists() else []
    return {"release": release(), "apks": apks}


@router.post("/release")
def release_set(body: ReleaseIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(ServerSetting, "release")
    if row is None:
        row = ServerSetting(key="release", value={})
        db.add(row)
    row.value = {k: v for k, v in body.model_dump().items() if v is not None or k == "url"}
    _log(db, who, "release_set", **row.value)
    db.commit()
    return {"release": row.value}


@router.post("/apk")
async def apk_upload(request: Request, name: str = Query(pattern=r"^[A-Za-z0-9._\-]{3,80}\.apk$"), who: str = Depends(admin)):
    """Streams an APK into the downloads folder (raw request body)."""
    d = get_settings().downloads_path
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".part")
    size = 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > 300 * 1024 * 1024:
                f.close()
                tmp.unlink(missing_ok=True)
                raise GameError("too_big", "APK больше 300 МБ", 413)
            f.write(chunk)
    with tmp.open("rb") as f:
        if f.read(2) != b"PK":
            tmp.unlink(missing_ok=True)
            raise GameError("bad_apk", "Это не APK-файл", 400)
    tmp.replace(d / name)
    return {"name": name, "size": size}


# ------------------------------------------------------------------ game events
@router.get("/events")
def events_list(who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..social.common import cfg
    ev = cfg()["events"]["templates"]
    tt = cfg()["tournaments"]["templates"]
    raids = []
    for kind in ("world", "seasonal"):
        inst = db.scalar(select(RaidInstance).where(RaidInstance.kind == kind, RaidInstance.status == "active"))
        raids.append({"kind": kind, "boss": inst.boss_code if inst else None, "hp_left": inst.hp_left if inst else None,
                      "hp_max": inst.hp_max if inst else None})
    return {
        "templates": [{"code": k, "name": v["name"], "kind": v["kind"], "days": v["days"], "goal": v["goal"], "desc": v["desc"]} for k, v in ev.items()],
        "active": [{"id": e.id, "name": e.name, "progress": e.progress, "goal": e.goal, "status": e.status,
                    "ends_at": as_utc(e.ends_at).isoformat()} for e in db.scalars(select(WorldEvent).order_by(WorldEvent.starts_at.desc()).limit(10))],
        "tournament_templates": [{"code": k, "name": v["name"], "kind": v["kind"], "format": v["format"]} for k, v in tt.items()],
        "tournaments": [{"id": t.id, "name": t.name, "status": t.status, "reg_ends_at": as_utc(t.reg_ends_at).isoformat()}
                        for t in db.scalars(select(Tournament).where(Tournament.status != "finished").order_by(Tournament.reg_ends_at))],
        "raids": raids,
    }


class EventStartIn(BaseModel):
    template: str = Field(max_length=32)
    hours: int = Field(default=72, ge=1, le=24 * 31)
    goal: int | None = Field(default=None, ge=1000, le=10**10)
    announce: bool = True


@router.post("/events/start")
def event_start(body: EventStartIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..social.chat import system_message
    from ..social.common import cfg
    tpl = cfg()["events"]["templates"].get(body.template)
    if tpl is None:
        raise GameError("not_found", "Нет такого шаблона события", 404)
    now = utcnow()
    e = WorldEvent(code=f"{body.template}:admin-{now.strftime('%Y%m%d%H%M%S')}", template=body.template, name=tpl["name"],
                   kind=tpl["kind"], scale="admin", starts_at=now, ends_at=now + timedelta(hours=body.hours),
                   goal=body.goal or tpl["goal"], progress=0, choice_votes={})
    db.add(e)
    if body.announce:
        system_message(db, "global", f"Событие «{tpl['name']}» началось! Общая цель сервера — {e.goal:,}.".replace(",", " "))
    _log(db, who, "event_start", template=body.template, hours=body.hours, goal=e.goal)
    db.commit()
    return {"id": e.id}


@router.post("/events/{event_id}/finish")
def event_finish(event_id: str, who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..social.events import finish
    e = db.get(WorldEvent, event_id)
    if e is None or e.status != "active":
        raise GameError("not_found", "Событие не активно", 404)
    e.ends_at = utcnow()
    finish(db, e)
    _log(db, who, "event_finish", event=event_id, outcome=e.outcome)
    db.commit()
    return {"outcome": e.outcome}


class RaidIn(BaseModel):
    kind: str = Field(pattern="^(world|seasonal)$")


@router.post("/raids/respawn")
def raid_respawn(body: RaidIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """Ends the current shared boss (participation rewards) and spawns a fresh one."""
    from ..social.chat import system_message
    from ..social.raids import boss_conf, current_instance, finish
    inst = db.scalar(select(RaidInstance).where(RaidInstance.kind == body.kind, RaidInstance.status == "active"))
    if inst is not None:
        finish(db, inst, expired=True)
        db.flush()
    new = current_instance(db, body.kind, None)
    system_message(db, "global", f"Начался рейд на босса: {boss_conf(new.boss_code)['name']}!")
    _log(db, who, "raid_respawn", kind=body.kind)
    db.commit()
    return {"raid_id": new.id}


class TournamentIn(BaseModel):
    template: str = Field(max_length=32)
    reg_hours: int = Field(default=24, ge=1, le=24 * 14)


@router.post("/tournaments/create")
def tournament_create(body: TournamentIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    from ..social.chat import system_message
    from ..social import tournaments as TS
    tpl = TS.T()["templates"].get(body.template)
    if tpl is None:
        raise GameError("not_found", "Нет такого шаблона турнира", 404)
    tpl = {**tpl, "reg_hours": body.reg_hours}
    start = utcnow()
    t = TS._ensure_one(db, body.template, tpl, start, "admin-" + start.strftime("%Y%m%d%H%M%S"))
    system_message(db, "global", f"Открыта регистрация на турнир «{t.name}»!")
    _log(db, who, "tournament_create", template=body.template)
    db.commit()
    return {"id": t.id}


CURRENCY_KEYS = {"gold", "crystals", "summon_essence", "nature_essence", "ancient_seals", "guild_marks", "friend_tokens", "raid_tickets"}


class MailAllIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=2000)
    rewards: dict[str, int] = Field(default_factory=dict)
    active_days: int = Field(default=30, ge=1, le=3650)


@router.post("/mail-all")
def mail_all(body: MailAllIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    """One mail to every real player seen in the last N days (gift giveaways, announcements)."""
    rewards = {k: int(v) for k, v in body.rewards.items() if k in CURRENCY_KEYS and 0 < int(v) <= 1_000_000}
    msg = MailMessage(title=body.title, body=body.body, attachments=rewards, sender="Администрация")
    db.add(msg)
    db.flush()
    since = utcnow() - timedelta(days=body.active_days)
    n = 0
    for uid in db.scalars(select(PlayerProfile.user_id).where(PlayerProfile.is_ai.is_(False),
                                                              PlayerProfile.last_seen_at >= since)):
        db.add(PlayerMail(user_id=uid, message_id=msg.id, expires_at=utcnow() + timedelta(days=30)))
        n += 1
    _log(db, who, "mail_all", title=body.title, rewards=rewards, recipients=n)
    db.commit()
    return {"recipients": n}


# ------------------------------------------------------------------ admin chat
ADMIN_PREFIX = "📢 Администрация: "


@router.get("/chat")
def chat_recent(channel: str = Query("global", max_length=80), who: str = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatMessage).where(ChatMessage.channel == channel).order_by(ChatMessage.id.desc()).limit(80)).all()
    out = []
    for m in rows:
        p = db.get(PlayerProfile, m.user_id) if m.user_id else None
        out.append({"id": m.id, "author": p.nickname if p else "Система", "uralia_id": p.uralia_id if p else None,
                    "is_ai": m.is_ai, "text": m.text, "hidden": m.hidden, "at": as_utc(m.created_at).isoformat()})
    guilds = [{"channel": f"guild:{g.id}", "name": f"[{g.tag}] {g.name}"} for g in db.scalars(select(Guild).order_by(Guild.name))]
    from ..game import data as GD
    extra = [{"channel": "news", "name": "📣 Объявления"}] + [{"channel": f"region:{r['code']}", "name": "Регион: " + r["name"]}
                                                            for r in GD.REGIONS if r["code"] in {a for a, _ in GD.ROADS} | {b for _, b in GD.ROADS}]
    from ..social.channels import active_event
    ev = active_event(db)
    if ev is not None:
        extra.append({"channel": f"event:{ev.id}", "name": "Событие: " + ev.name})
    return {"messages": out, "guilds": extra + guilds}


class AdminChatIn(BaseModel):
    channel: str = Field(default="global", max_length=80)
    text: str = Field(min_length=1, max_length=380)


@router.post("/chat")
def chat_send(body: AdminChatIn, who: str = Depends(admin), db: Session = Depends(get_db)):
    if not (body.channel in ("global", "news") or re.match(r"^(guild|event|alliance|group):[0-9a-f\-]{36}$", body.channel)
            or re.match(r"^region:[a-z0-9_]{2,32}$", body.channel)):
        raise GameError("bad_channel", "Неизвестный канал")
    m = ChatMessage(channel=body.channel, user_id=None, text=(ADMIN_PREFIX + body.text.strip())[:400], reactions={})
    db.add(m)
    _log(db, who, "chat_send", channel=body.channel, text=body.text[:200])
    db.commit()
    return {"id": m.id}


# ------------------------------------------------------------------ art
@router.get("/art")
def art_catalog(who: str = Depends(admin)):
    idx = art.index()
    sections = art.catalog()
    for sec in sections:
        for s in sec["slots"]:
            s["staged"] = idx["files"].get(s["path"])
    return {"sections": sections, "published_version": idx.get("published_version", 0), "anim_keys": art.ANIM_KEYS,
            "models_version": idx.get("models_version", 0),
            "published_at": idx.get("published_at"), "dirty": bool(idx.get("dirty")) or any(not v.get("published") for v in idx["files"].values())}


@router.post("/art/upload")
async def art_upload(request: Request, path: str = Query(max_length=120), who: str = Depends(admin),
                     db: Session = Depends(get_db)):
    data = await request.body()
    try:
        meta = art.stage(path, data)
    except ValueError as e:
        raise GameError("bad_art", str(e), 400)
    _log(db, who, "art_upload", path=path, size=len(data))
    db.commit()
    return {"path": path, **meta}


class ModelSettingsIn(BaseModel):
    scale: float = Field(1.0, ge=0.05, le=20)
    anims: dict[str, str] = Field(default_factory=dict)


@router.post("/art/model-settings")
def art_model_settings(body: ModelSettingsIn, path: str = Query(max_length=120), who: str = Depends(admin),
                       db: Session = Depends(get_db)):
    """Animation mapping (game action -> animation in the GLB) and scale of an uploaded 3D model."""
    try:
        meta = art.set_model_settings(path, body.scale, body.anims)
    except ValueError as e:
        raise GameError("bad_model", str(e), 400)
    _log(db, who, "art_model_settings", path=path, scale=body.scale, anims=body.anims)
    db.commit()
    return {"path": path, **meta, "anim_keys": art.ANIM_KEYS}


@router.post("/art/remove")
def art_remove(path: str = Query(max_length=120), who: str = Depends(admin), db: Session = Depends(get_db)):
    art.unstage(path)
    _log(db, who, "art_remove", path=path)
    db.commit()
    return {"ok": True}


@router.get("/art/file")
def art_file(path: str = Query(max_length=120), who: str = Depends(admin)):
    f = art.staged_file(path)
    if f is None:
        raise GameError("not_found", "Файл не загружен", 404)
    head = f.read_bytes()[:4]
    if head == b"glTF":
        return FileResponse(f, media_type="model/gltf-binary")
    return FileResponse(f, media_type="image/jpeg" if head[:3] == b"\xff\xd8\xff" else "image/png")


@router.post("/art/publish")
def art_publish(who: str = Depends(admin), db: Session = Depends(get_db)):
    res = art.publish(db, who)
    _log(db, who, "art_publish", **res)
    db.commit()
    return res
