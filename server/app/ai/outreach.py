"""Interaction with real players (stage 16): AI residents may start a friendly conversation, congratulate on
achievements, offer help, invite to guilds and events, remember players and past meetings, develop friendship and
rivalry, react to deeds and to absence.

Always: the player's privacy settings ("AI may write to me first") and blocks are respected; per-player limits per day
and per week; a global hourly limit; administration exceptions (never contact a player / a persona never initiates);
AI are labelled as AI in every message (the chat UI marks AI authors); only players online right now are contacted."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import (
    AiActivityLog, AiPersona, AiPlayerWatch, ChatMessage, GuildApplication, GuildMember, Guild, PlayerProfile,
    ServerSetting, UserBlock, WorldEventContribution,
)
from .sections import Section

SECTION = Section(
    "ai_outreach",
    {"initiative": 50, "friendliness": 70, "aggressiveness": 20, "dm_per_player_day": 2, "invites_per_player_week": 2,
     "global_per_hour": 30, "absence_days": 3, "congratulate": True, "welcome_new": True, "welcome_back": True,
     "offer_help": True, "invite_guild": True, "invite_events": True, "rivalry_messages": True, "first_contact": True,
     "flirt": True, "flirt_per_player_week": 3, "flirt_ignored_stop": 2},
    {"initiative": ("int", 0, 100), "friendliness": ("int", 0, 100), "aggressiveness": ("int", 0, 100),
     "dm_per_player_day": ("int", 0, 10), "invites_per_player_week": ("int", 0, 14), "global_per_hour": ("int", 0, 500),
     "absence_days": ("int", 1, 60), "congratulate": ("bool",), "welcome_new": ("bool",), "welcome_back": ("bool",),
     "offer_help": ("bool",), "invite_guild": ("bool",), "invite_events": ("bool",), "rivalry_messages": ("bool",),
     "first_contact": ("bool",), "flirt": ("bool",), "flirt_per_player_week": ("int", 0, 21),
     "flirt_ignored_stop": ("int", 1, 10)},
    {"initiative": "Инициативность ИИ, %", "friendliness": "Дружелюбие, %",
     "aggressiveness": "Дух соперничества (дружеские подначки после арены), %",
     "dm_per_player_day": "Сообщений от ИИ одному игроку в день, максимум",
     "invites_per_player_week": "Приглашений одному игроку в неделю, максимум",
     "global_per_hour": "Первых сообщений ИИ игрокам в час, всего", "absence_days": "Через сколько дней отсутствия «давно не виделись»",
     "congratulate": "Поздравлять с достижениями", "welcome_new": "Приветствовать новичков",
     "welcome_back": "Радоваться возвращению", "offer_help": "Предлагать помощь новичкам",
     "invite_guild": "Приглашать в гильдии ИИ", "invite_events": "Приглашать на события",
     "rivalry_messages": "Писать после боёв на арене", "first_contact": "Иногда первыми заводить знакомство",
     "flirt": "18+: ИИ флиртуют с взрослыми игроками в личке (если у игрока включено 18+)",
     "flirt_per_player_week": "18+: флирт-сообщений одному игроку в неделю, максимум",
     "flirt_ignored_stop": "18+: замолчать, если игрок не ответил на столько флирт-сообщений подряд"})
EXC_KEY = "ai_outreach_exceptions"

LINES = {
    "welcome_new": ["Привет, {name}! Вижу, ты новенький в Уралии 🙂 Если что непонятно — пиши, подскажу.",
                    "Салам, {name}! Добро пожаловать. Я тут давно, могу рассказать, с чего начать.",
                    "{name}, привет! Рад новому лицу. Совет: не забывай забирать сундук дозора."],
    "congratulate": ["{name}, поздравляю с {lvl} уровнем! 🎉", "О, {name} уже {lvl} уровня! Красиво растёшь 💪",
                     "{lvl} уровень, {name}? Респект! Дальше — больше."],
    "welcome_back": ["{name}! Давно тебя не было. Как ты? 🙂", "О, {name} вернулся! Мы уж думали, тебя Аждаха утащила 😄",
                     "{name}, с возвращением! Тут без тебя было тише."],
    "offer_help": ["{name}, если застрял в кампании — поставь танка вперёд и лекаря назад, сразу легче.",
                   "Совет от старого лучника, {name}: смотри фракцию врага, преимущество даёт +20% урона.",
                   "{name}, не держи эссенцию — призывай героев, коллекция решает."],
    "invite_guild": ["{name}, заходи к нам в «{guild}»! Приглашение уже ждёт тебя в гильдиях 🙂",
                     "У нас в «{guild}» дружно, {name}. Отправил приглашение — будем рады!"],
    "invite_event": ["{name}, идёт событие «{event}» — присоединяйся, вместе веселее!",
                     "Не пропусти «{event}», {name}! Мы уже вовсю участвуем 🔥"],
    "first_contact": ["Привет, {name}! Видел тебя в чате, решил познакомиться 🙂", "{name}, хай! Как успехи в Уралии?",
                      "Здорово, {name}! Ты за какую фракцию больше любишь играть?"],
    "rival_win": ["{name}, твоя защита держалась достойно, но в этот раз моя взяла 😏 Реванш?",
                  "Хороший бой, {name}! Подтяни танка — и будет интересно."],
    "rival_loss": ["{name}, ну и защита у тебя! Я не пробился 😅 Уважаю.", "Эх, {name}, твоя команда крепкая. В следующий раз отыграюсь!"],
}
SOFT = {"welcome_new": "Привет, {name}. Добро пожаловать в Уралию.", "congratulate": "Поздравляю с {lvl} уровнем, {name}.",
        "welcome_back": "С возвращением, {name}.", "first_contact": "Привет, {name}."}


# ------------------------------------------------------------------ privacy, limits, exceptions
def exceptions(db: Session) -> dict:
    row = db.get(ServerSetting, EXC_KEY)
    v = dict(row.value or {}) if row else {}
    return {"players": list(v.get("players", [])), "personas": list(v.get("personas", []))}


def set_exceptions(db: Session, players: list[str] | None, personas: list[str] | None) -> dict:
    row = db.get(ServerSetting, EXC_KEY)
    if row is None:
        row = ServerSetting(key=EXC_KEY, value={})
        db.add(row)
    cur = exceptions(db)
    if players is not None:
        cur["players"] = sorted(set(players))[:5000]
    if personas is not None:
        cur["personas"] = sorted(set(personas))[:5000]
    row.value = cur
    return cur


def may_contact(db: Session, player: PlayerProfile, persona: AiPersona | None = None) -> tuple[bool, str]:
    from ..social.ai.control import player_prefs
    from ..social.channels import SECTION as CHS
    if player is None or player.is_ai:
        return False, "not a player"
    from ..social.ai.control import dm_allowed
    if not dm_allowed(player):
        return False, "minor or age not set"  # decision D-C1: AI never write privately to minors / unknown age
    if not CHS.get(db)["ai_dm_first"]:
        return False, "channel off"
    if not player_prefs(player).get("ai_contact", True):
        return False, "player opted out"
    exc = exceptions(db)
    if player.user_id in exc["players"]:
        return False, "admin exception"
    if persona is not None:
        if persona.id in exc["personas"] or not persona.active:
            return False, "persona excluded"
        if db.get(UserBlock, (player.user_id, persona.user_id)) or db.get(UserBlock, (persona.user_id, player.user_id)):
            return False, "blocked"
    return True, "ok"


def watch(db: Session, user_id: str) -> AiPlayerWatch:
    from ..social.common import day, week_key
    w = db.get(AiPlayerWatch, user_id)
    if w is None:
        w = AiPlayerWatch(user_id=user_id, level=0, day=day(), contacts_today=0, week=week_key(), invites_week=0, flags={})
        db.add(w)
        db.flush()
    if w.day != day():
        w.day, w.contacts_today = day(), 0
    if w.week != week_key():
        w.week, w.invites_week = week_key(), 0
    return w


def _global_left(db: Session, s: dict) -> int:
    since = utcnow() - timedelta(hours=1)
    n = db.scalar(select(func.count()).select_from(AiActivityLog).where(AiActivityLog.activity == "outreach",
                                                                         AiActivityLog.created_at >= since)) or 0
    return int(s["global_per_hour"]) - n


# ------------------------------------------------------------------ sending
def _pick_persona(db: Session, player: PlayerProfile, rng: random.Random, prefer: str = "") -> AiPersona | None:
    from . import social as SOC
    cands = []
    for r in SOC.who_likes(db, player.user_id, 0.2, 8):
        p = db.scalar(select(AiPersona).where(AiPersona.user_id == r.subject_id))
        if p is not None:
            cands.append(p)
    if not cands:
        q = select(AiPersona).where(AiPersona.active.is_(True)).order_by(func.random()).limit(25)
        pool = list(db.scalars(q))
        if prefer == "mentor":
            pool.sort(key=lambda p: -((p.traits or {}).get("generosity", 0.5) + ("mentor" in (p.ambitions or [])) * 0.5))
        else:
            pool.sort(key=lambda p: -(p.traits or {}).get("sociability", 0.5))
        cands = pool[:5]
    for p in cands:
        if may_contact(db, player, p)[0]:
            return p
    return None


def _text(rng: random.Random, kind: str, s: dict, **kw) -> str:
    warm = rng.random() * 100 < s["friendliness"]
    tpl = rng.choice(LINES[kind]) if (warm or kind not in SOFT) else SOFT[kind]
    try:
        return tpl.format(**kw)
    except (KeyError, IndexError):
        return tpl


def send(db: Session, persona: AiPersona, player: PlayerProfile, kind: str, text: str, rng: random.Random,
         invite: bool = False) -> None:
    from ..social.ai.population import log
    from ..social.chat import dm_channel
    from . import memory as MEM
    from . import social as SOC
    from . import speech as SP
    final = SP.stylize(rng, persona, text, {**SP.SECTION.get(db), "length": "medium"})
    db.add(ChatMessage(channel=dm_channel(persona.user_id, player.user_id), user_id=persona.user_id, text=final[:300],
                       is_ai=True, reactions={}))
    w = watch(db, player.user_id)
    w.contacts_today = (w.contacts_today or 0) + 1
    w.contacted_at = utcnow()
    if invite:
        w.invites_week = (w.invites_week or 0) + 1
    MEM.add(db, persona, "promise" if kind in ("offer_help", "invite_guild") else "conversation",
            f"Написал первым ({kind}) игроку {player.nickname}", subject=player.user_id, importance=2 if invite else 1)
    SOC.relate(db, persona.user_id, player.user_id, {"congratulate": "congrats", "offer_help": "help"}.get(kind, "dm"))
    log(db, persona, "outreach", kind=kind, to=player.user_id)


# ------------------------------------------------------------------ triggers
def _guild_to_invite(db: Session) -> tuple[Guild, AiPersona] | None:
    from ..social.guilds import G, member_count
    for g in db.scalars(select(Guild).where(Guild.is_ai.is_(True)).order_by(func.random()).limit(5)):
        if member_count(db, g.id) >= G()["max_members"] - 2:
            continue
        officer = db.scalar(select(AiPersona).join(GuildMember, GuildMember.user_id == AiPersona.user_id)
                            .where(GuildMember.guild_id == g.id, GuildMember.role.in_(("leader", "deputy", "officer")))
                            .limit(1))
        if officer:
            return g, officer
    return None


def consider(db: Session, player: PlayerProfile, rng: random.Random, s: dict) -> str | None:
    """Decides whether and how the AI residents reach out to this online player now. Returns the trigger used."""
    from ..social.channels import SECTION as CHS, active_event
    w = watch(db, player.user_id)
    ok, _ = may_contact(db, player)
    prev_level, prev_seen = w.level or 0, w.seen_at
    w.level, w.seen_at = player.level, utcnow()
    if not ok or (w.contacts_today or 0) >= s["dm_per_player_day"]:
        return None
    if w.contacted_at and utcnow() - as_utc(w.contacted_at) < timedelta(minutes=20):
        return None  # never several AI messages in a row
    flags = dict(w.flags or {})
    name = player.nickname
    init = s["initiative"] / 100.0
    trigger = None
    created = as_utc(player.created_at) if player.created_at else utcnow()
    if s["welcome_new"] and not flags.get("greeted") and utcnow() - created < timedelta(days=2):
        trigger = "welcome_new"
    elif s["congratulate"] and prev_level and player.level // 5 > prev_level // 5 and rng.random() < 0.5 + init / 2:
        trigger = "congratulate"
    elif s["welcome_back"] and prev_seen and utcnow() - as_utc(prev_seen) > timedelta(days=int(s["absence_days"])):
        trigger = "welcome_back"
    elif s["offer_help"] and player.level <= 10 and not flags.get("helped") and rng.random() < init:
        trigger = "offer_help"
    elif CHS.get(db)["ai_invites"] and (w.invites_week or 0) < s["invites_per_player_week"]:
        in_guild = db.scalar(select(GuildMember).where(GuildMember.user_id == player.user_id)) is not None
        ev = active_event(db)
        if s["invite_guild"] and not in_guild and player.level >= 5 and rng.random() < init * 0.6:
            trigger = "invite_guild"
        elif s["invite_events"] and ev is not None and not flags.get(f"ev_{ev.id}") and \
                db.get(WorldEventContribution, (ev.id, player.user_id)) is None and rng.random() < init * 0.5:
            trigger = "invite_event"
    if trigger is None and s["first_contact"] and not flags.get("met") and rng.random() < init * 0.15:
        trigger = "first_contact"
    if trigger is None and _flirt_ok(db, player, w, flags, s) and rng.random() < init * 0.35:
        trigger = "flirt"
    if trigger is None:
        return None
    if trigger == "flirt":
        from . import adult as ADULT
        cands = [p for p in db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).order_by(func.random()).limit(40))
                 if ADULT.flirt_persona_ok(p) and may_contact(db, player, p)[0]]
        if not cands:
            return None
        pref = [p for p in cands if ADULT.prefer_for(player.gender, p)]
        persona = (pref or cands)[0]
        send(db, persona, player, "flirt", ADULT.opener(rng, player.nickname, player.gender), rng)
        fl = dict(w.flags or {})
        fl["flirt_week"] = {"week": w.week, "n": int((fl.get("flirt_week") or {}).get("n", 0)) + 1 if (fl.get("flirt_week") or {}).get("week") == w.week else 1}
        fl["flirt_unanswered"] = int(fl.get("flirt_unanswered", 0)) + 1
        fl["met"] = True
        w.flags = fl
        return trigger
    if trigger == "invite_guild":
        pick = _guild_to_invite(db)
        if pick is None:
            return None
        g, persona = pick
        if not may_contact(db, player, persona)[0]:
            return None
        if not db.scalar(select(GuildApplication).where(GuildApplication.guild_id == g.id, GuildApplication.user_id == player.user_id,
                                                        GuildApplication.status == "pending")):
            db.add(GuildApplication(guild_id=g.id, user_id=player.user_id, kind="invite", invited_by=persona.user_id))
        send(db, persona, player, trigger, _text(rng, "invite_guild", s, name=name, guild=g.name), rng, invite=True)
    else:
        persona = _pick_persona(db, player, rng, "mentor" if trigger == "offer_help" else "")
        if persona is None:
            return None
        kw = {"name": name, "lvl": player.level}
        if trigger == "invite_event":
            ev = active_event(db)
            kw["event"] = ev.name
            flags[f"ev_{ev.id}"] = True
        send(db, persona, player, trigger, _text(rng, trigger if trigger != "invite_event" else "invite_event", s, **kw), rng,
             invite=trigger == "invite_event")
    flags.update({"greeted": flags.get("greeted") or trigger == "welcome_new", "helped": flags.get("helped") or trigger == "offer_help",
                  "met": True})
    w.flags = flags
    return trigger


def _flirt_ok(db: Session, player: PlayerProfile, w: AiPlayerWatch, flags: dict, s: dict) -> bool:
    """18+ flirt outreach: adult with the setting on, not asked to stop, not ignoring us, within the weekly limit."""
    from ..social.ai.control import adult_ok
    if not s.get("flirt") or not adult_ok(player) or flags.get("no_flirt"):
        return False
    if int(flags.get("flirt_unanswered", 0)) >= int(s["flirt_ignored_stop"]):
        return False
    fw = flags.get("flirt_week") or {}
    return not (fw.get("week") == w.week and int(fw.get("n", 0)) >= int(s["flirt_per_player_week"]))


def player_replied(db: Session, player_id: str, text: str) -> None:
    """Called when a real player writes to an AI privately: resets the 'ignored' counter; a stop phrase ends flirting."""
    from . import adult as ADULT
    w = db.get(AiPlayerWatch, player_id)
    if w is None:
        return
    fl = dict(w.flags or {})
    fl["flirt_unanswered"] = 0
    if ADULT.is_stop(text):
        fl["no_flirt"] = True
    w.flags = fl


def run(db: Session, rng: random.Random, limit: int = 30) -> dict:
    s = SECTION.get(db)
    left = _global_left(db, s)
    since = utcnow() - timedelta(minutes=3)
    online = list(db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)
                             .order_by(func.random()).limit(limit)))
    done: dict = {}
    for p in online:
        if left <= 0:
            break
        t = consider(db, p, rng, s)
        if t:
            done[t] = done.get(t, 0) + 1
            left -= 1
    db.flush()
    return {"online": len(online), "sent": done}


def after_arena(db: Session, persona: AiPersona, player_id: str, ai_won: bool, rng: random.Random | None = None) -> bool:
    """Friendly rivalry message after an AI's training fight against a real player's defense (aggressiveness)."""
    s = SECTION.get(db)
    rng = rng or random.Random()
    if not s["rivalry_messages"] or rng.random() * 100 >= s["aggressiveness"]:
        return False
    player = db.get(PlayerProfile, player_id)
    w = watch(db, player_id) if player else None
    if player is None or not may_contact(db, player, persona)[0] or (w.contacts_today or 0) >= s["dm_per_player_day"]:
        return False
    if _global_left(db, s) <= 0:
        return False
    send(db, persona, player, "rivalry", _text(rng, "rival_win" if ai_won else "rival_loss", s, name=player.nickname), rng)
    return True


def history(db: Session, user_id: str, limit: int = 60) -> list[dict]:
    """All AI <-> player direct messages (newest first) for the admin panel."""
    rows = db.scalars(select(ChatMessage).where(ChatMessage.channel.like(f"dm:%{user_id}%")).order_by(ChatMessage.id.desc())
                      .limit(limit * 3)).all()
    out = []
    for m in rows:
        ids = m.channel.split(":")[1:]
        other = next((x for x in ids if x != user_id), None)
        op = db.get(PlayerProfile, other) if other else None
        if op is None or not op.is_ai:
            continue
        out.append({"at": as_utc(m.created_at).isoformat(), "ai": op.nickname, "from_ai": m.user_id == other, "text": m.text})
        if len(out) >= limit:
            break
    return out
