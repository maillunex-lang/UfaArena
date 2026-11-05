"""AI Population Engine: population_manager, persona_registry, behavior_scheduler, dialogue (see dialogue.py),
memory_store, activity_simulator, guild_ai_controller, matchmaking_adapter (separate AI ladder) and audit log.

Rules: every persona is flagged is_ai and labelled in the UI; personas never buy, never touch real rankings,
never add to real event progress, never attack shared real raid bosses; total actions per tick and per day
are capped to protect the server."""
from __future__ import annotations

import random
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.db import as_utc, utcnow
from ...game import data as D
from ...models import (
    AiActivityLog, AiPersona, ArenaMatch, ArenaProfile, ChatMessage, FortressBuilding, Formation,
    FriendGift, FriendRequest, Friendship, Guild, GuildApplication, GuildMember, GuildUpgrade, PlayerHero,
    PlayerProfile, RaidInstance, Tournament, User, WorldEvent,
)
from ..common import cfg, compute_power, day, freeze_squad, league_of, pvp, squad_power
from . import dialogue as DLG
from . import personas as PR

_rng = random.Random()
# Reply and mention queues live in the database (ai_events, Living World AI phase 2): restarts lose nothing and the
# separate AI Director process sees the same queue.


def AI() -> dict:
    return cfg()["ai"]


def log(db: Session, persona: AiPersona, activity: str, **payload) -> None:
    db.add(AiActivityLog(persona_id=persona.id, activity=activity, payload=payload))


# ------------------------------------------------------------------ persona registry
def _summonable(db: Session | None = None) -> list[dict]:
    """Heroes an AI may own: the live table (admin-created, edited and disabled heroes respected)."""
    if db is not None:
        from ...models import Hero
        rows = db.scalars(select(Hero).where(Hero.summonable.is_(True), Hero.is_enemy.is_(False))).all()
        out = [{"code": h.code, "rarity": h.rarity, "class_code": h.class_code} for h in rows
               if not (h.extra or {}).get("disabled")]
        if out:
            return out
    return [h for h in D.HEROES if h.get("summonable", True) and not h.get("is_enemy")]


def create_persona(db: Session, rng: random.Random | None = None) -> AiPersona:
    from ...ai import memory as MEM
    from ...ai import personality as PERS
    from ...ai import tiers as TR
    rng = rng or _rng
    spec = PR.make(rng)
    # Living World AI phase 3: archetype from the editable table, power tier, individual personality
    arch = PERS.pick_archetype(db, rng)
    tier = TR.pick(rng, TR.SECTION.get(db))
    spec["archetype"] = arch.code
    spec["interests"] = list(arch.interests or spec["interests"])
    spec["style"] = rng.choice(arch.styles) if arch.styles else spec["style"]
    spec["level"] = TR.level_for(rng, tier, PR.ARCHETYPES.get(arch.code, {}).get("lvl"))
    strategy = rng.choice(TR.TIERS[tier]["strategies"])
    nick = spec["nickname"]
    while db.scalar(select(PlayerProfile).where(PlayerProfile.nickname == nick)):
        nick = f"{spec['nickname'][:20]}{rng.randrange(10, 99)}"
    from ...services import _uralia_id
    u = User(kind="ai")
    db.add(u)
    db.flush()
    created = utcnow() - timedelta(days=rng.randint(3, 120))  # a believable account age
    p = PlayerProfile(user_id=u.id, uralia_id=_uralia_id(db), nickname=nick, level=spec["level"], is_ai=True,
                      avatar=spec["avatar"], afk_last_claim_at=utcnow(), created_at=created,
                      cosmetics={"frame": spec["frame"]} if spec["frame"] else {},
                      last_seen_at=utcnow() - timedelta(hours=rng.randint(1, 30)))
    db.add(p)
    pool = _summonable(db)
    n_heroes = min(len(pool), rng.randint(*TR.TIERS[tier]["heroes"]))
    picks = rng.sample(pool, n_heroes)
    weights = sorted(picks, key=lambda h: -h["rarity"])
    ids = []
    s_lo, s_hi = TR.TIERS[tier]["stars"]
    for h in weights:
        lv = max(1, min(D.LEVEL_CAP_MVP, spec["level"] + rng.randint(-6, 3)))
        stars = rng.randint(s_lo, s_hi) if h["rarity"] <= 4 else min(1, rng.randint(s_lo, s_hi))
        ph = PlayerHero(user_id=u.id, hero_code=h["code"], level=lv, stars=stars)
        db.add(ph)
        db.flush()
        ids.append((ph.id, h))
    n_tanks = {"defensive": 2, "aggressive": 1}.get(strategy, 2 if rng.random() < 0.6 else 1)
    tanks = [i for i, h in ids if h["class_code"] in ("guardian", "warrior")][:n_tanks]
    rest = [i for i, h in ids if i not in tanks]
    slots = (tanks + rest)[:5]
    db.add(Formation(user_id=u.id, kind="campaign", slots=(slots + [None] * 5)[:5]))
    for code in D.BUILDINGS:
        db.add(FortressBuilding(user_id=u.id, code=code, level=max(1, min(10, spec["level"] // 6 + rng.randint(0, 2)))))
    persona = AiPersona(user_id=u.id, archetype=spec["archetype"], temperament=spec["temperament"],
                        backstory=spec["backstory"], style=spec["style"], schedule=spec["schedule"],
                        interests=spec["interests"], next_action_at=utcnow() + timedelta(seconds=rng.randint(20, 600)),
                        day=day(), tier=tier, pace=round(TR.TIERS[tier]["pace"] * rng.uniform(0.85, 1.15), 2),
                        personality_version=1)
    PERS.apply_generated(persona, PERS.generate(rng, arch))
    persona.counters = {"strategy": strategy}
    db.add(persona)
    db.flush()
    MEM.checkpoint(db, persona, "Характер при создании")
    MEM.bio_add(db, persona, "created", f"{spec['backstory']} Начал как {TR.TIERS[tier]['name'].lower()}, "
                                        f"тактика — {TR.STRATEGY_NAMES[strategy].lower()}.")
    compute_power(db, u.id)
    spec_sq = freeze_squad(db, u.id)
    db.add(ArenaProfile(user_id=u.id, rating=1000 + rng.randint(-150, 250), defense=spec_sq,
                        defense_power=squad_power(spec_sq), is_ai=True, day=day()))
    log(db, persona, "created", archetype=spec["archetype"], style=spec["style"], tier=tier)
    return persona


def target_population(db: Session) -> int:
    since = utcnow() - timedelta(days=7)
    real = db.scalar(select(func.count()).select_from(PlayerProfile).where(
        PlayerProfile.is_ai.is_(False), PlayerProfile.last_seen_at >= since)) or 0
    return int(max(AI()["min_population"], min(AI()["target_population"], real * AI()["real_players_ratio"])))


def ensure_population(db: Session, max_new: int = 5) -> dict:
    """Adaptive population: grows towards the target a few personas per run, retires extras (kept, inactive)."""
    target = target_population(db)
    active = db.scalars(select(AiPersona).where(AiPersona.active.is_(True))).all()
    if len(active) < AI()["min_population"]:
        max_new = max(max_new, AI()["min_population"] - len(active))  # first start: fill the world at once
    created = 0
    while len(active) + created < target and created < max_new:
        create_persona(db)
        created += 1
    retired = 0  # Living World AI stage 3: fewer active personas is handled by sessions, profiles stay enabled
    db.flush()
    from ...ai import personality as PERS
    PERS.ensure(db, 50)  # phase 3: personalities and tiers for personas created earlier (progress unchanged)
    _refresh_styles(db)
    ensure_ai_guilds(db)
    return {"target": target, "active": len(active) + created - retired, "created": created, "retired": retired}


NEW_STYLES = ("joker", "grumpy", "flirty", "bro")


def _refresh_styles(db: Session) -> None:
    """Personas created before the bigger character set get some of the new characters (once)."""
    rows = db.scalars(select(AiPersona)).all()
    if not rows:
        return
    flirty = [p for p in rows if p.style == "flirty"]
    if len(flirty) > max(3, len(rows) // 8):  # keep flirting a spice, not the main course
        for p in flirty[max(3, len(rows) // 8):]:
            p.style = _rng.choice(["joker", "bro", "grumpy", "friendly"])
    if any(p.style in NEW_STYLES for p in rows):
        return
    for p in rows:
        if _rng.random() < 0.5:
            p.style = _rng.choices(NEW_STYLES, weights=[3, 2, 1, 3])[0]


# ------------------------------------------------------------------ guild AI controller
AI_GUILD_NAMES = [("Дети Урала", "УРАЛ"), ("Ветер Ирендыка", "ВЕТЕР"), ("Каменный Курай", "КУРАЙ"),
                  ("Беркуты Шиханов", "БРКТ"), ("Стража Агидели", "АГДЛ"), ("Тропа Иремеля", "ИРМЛ")]


def ensure_ai_guilds(db: Session) -> int:
    have = db.scalars(select(Guild).where(Guild.is_ai.is_(True))).all()
    for g in have:  # virtual guilds always welcome newcomers (the guild must never be locked for a new player)
        g.min_level = 1
    made = 0
    used: set[str] = set()
    for name, tag in AI_GUILD_NAMES[: AI()["ai_guilds"]]:
        if any(g.name == name for g in have):
            continue
        db.flush()
        free = [p for p in db.scalars(select(AiPersona).where(AiPersona.active.is_(True)))
                if p.user_id not in used and db.scalar(select(GuildMember).where(GuildMember.user_id == p.user_id)) is None]
        if len(free) < 6:
            break
        _rng.shuffle(free)
        leader = max(free[:12], key=lambda p: db.get(PlayerProfile, p.user_id).level)
        spec = _rng.choice(["warriors", "hunters", "keepers"])
        g = Guild(name=name, tag=tag, description="Виртуальная гильдия ИИ-персонажей. Новички приветствуются!",
                  join_mode="approval", min_level=1, leader_id=leader.user_id, is_ai=True,
                  specialization=spec, treasury=_rng.randint(500, 3000))
        db.add(g)
        db.flush()
        db.add(GuildUpgrade(guild_id=g.id, code="hall", kind="building", level=_rng.randint(2, 4)))
        members = [leader] + [p for p in free[:12] if p.id != leader.id][: _rng.randint(6, 11)]
        roles = ["leader", "deputy", "officer", "officer", "veteran", "veteran"]
        for i, p in enumerate(members):
            used.add(p.user_id)
            db.add(GuildMember(guild_id=g.id, user_id=p.user_id, role=roles[i] if i < len(roles) else "member",
                               last_active_at=utcnow()))
        made += 1
    db.flush()
    return made


def ai_guild_review(db: Session, g: Guild, user_id: str) -> bool:
    p = db.get(PlayerProfile, user_id)
    return bool(p and p.level >= (g.min_level or 1))


def ai_accept_guild_invite(db: Session, ai_user_id: str, g: Guild) -> bool:
    persona = db.scalar(select(AiPersona).where(AiPersona.user_id == ai_user_id))
    return bool(persona and "guild" in (persona.interests or []) and _rng.random() < 0.7)


def ai_consider_friend(db: Session, ai_user_id: str, from_user: str) -> bool:
    persona = db.scalar(select(AiPersona).where(AiPersona.user_id == ai_user_id))
    if persona is None or not persona.active:
        return False
    chance = 0.95 if persona.style != "shy" else 0.75
    ok = _rng.random() < chance
    if ok:
        remember(db, persona, from_user, "Подружились", kind="relationship")
        from ...ai import personality as PERS
        from ...ai import social as SOC
        PERS.evolve(db, persona, "friend")
        SOC.relate(db, persona.user_id, from_user, "friend")
        from .control import dm_allowed
        if dm_allowed(db.get(PlayerProfile, from_user)):
            queue_reply(db, ai_user_id, from_user, None, "__welcome__")
    return ok


# ------------------------------------------------------------------ memory store
def remember(db: Session, persona: AiPersona, subject: str, fact: str, kind: str = "conversation",
             importance: float = 1.0) -> None:
    """Long-term memory (Living World AI stage 14): kept, later archived — never silently expires."""
    from ...ai import memory as MEM
    MEM.add(db, persona, kind, fact, subject=subject, importance=importance)


def recall(db: Session, persona: AiPersona, subject: str) -> list[str]:
    from ...ai import memory as MEM
    return [m.fact for m in MEM.recall(db, persona, subject=subject, limit=5)]


# ------------------------------------------------------------------ reply queues (filled by chat)
def queue_reply(db: Session, ai_user_id: str, to_user: str, channel: str | None, text: str) -> None:
    from ...ai import events as EV
    EV.emit(db, "dm", {"to_user": to_user, "channel": channel, "text": text[:300]}, persona_user_id=ai_user_id,
            delay_s=_rng.uniform(5, 40))  # a human-like pause before answering


def queue_mention(db: Session, channel: str, user_id: str, text: str) -> None:
    from ...ai import events as EV
    EV.emit(db, "mention", {"channel": channel, "user_id": user_id, "text": text[:300]})


def _context(db: Session, persona: AiPersona, to_user: str | None = None) -> dict:
    p = db.get(PlayerProfile, persona.user_id)
    ap = db.get(ArenaProfile, persona.user_id)
    ev = db.scalar(select(WorldEvent).where(WorldEvent.status == "active").order_by(WorldEvent.starts_at.desc()))
    raid = db.scalar(select(RaidInstance).where(RaidInstance.kind == "world", RaidInstance.status == "active"))
    t = db.scalar(select(Tournament).where(Tournament.status == "registration"))
    hero = db.scalar(select(PlayerHero).where(PlayerHero.user_id == persona.user_id).order_by(PlayerHero.level.desc()))
    ctx = {"lvl": p.level, "rating": ap.rating if ap else 1000, "league": league_of(ap.rating if ap else 1000)["name"],
           "hero": hero.hero.name if hero else "Азамат", "delta": _rng.randint(8, 60),
           "event": ev.name if ev else "событие", "event_pct": int(100 * ev.progress / ev.goal) if ev and ev.goal else 0,
           "tournament": t.name if t else "турнир", "boss": "Аждаха", "phase": "Пламя", "name": ""}
    if raid:
        from ..raids import boss_conf, phase_of
        b = boss_conf(raid.boss_code)
        ctx["boss"] = b["name"]
        ctx["phase"] = phase_of(b, raid.hp_left / raid.hp_max)[1]["name"]
    if to_user:
        tp = db.get(PlayerProfile, to_user)
        ctx["name"] = tp.nickname if tp else ""
    return ctx


def _say(db: Session, persona: AiPersona, channel: str, text: str) -> None:
    db.add(ChatMessage(channel=channel, user_id=persona.user_id, text=text[:300], is_ai=True, reactions={}))
    db.flush()


def handle_dm(db: Session, ai_uid: str, to_user: str, channel: str | None, text: str) -> bool:
    """Answer a direct message (or greet a new friend). Returns True when a message was written."""
    persona = db.scalar(select(AiPersona).where(AiPersona.user_id == ai_uid))
    if persona is None:
        return False
    from ...ai import speech as SP
    from .control import adult_ok, dm_allowed
    target = db.get(PlayerProfile, to_user)
    if target is not None and not target.is_ai and not dm_allowed(target):
        return False  # decision D-C1: never write privately to minors / unknown age
    ctx = _context(db, persona, to_user)
    from ...ai import adult as ADULT
    if text != "__welcome__" and (ADULT.is_flirt(text) or ADULT.heat_of(text) > 0) and not ADULT.is_stop(text):
        if adult_ok(target) and ADULT.flirt_persona_ok(persona):
            from ...models import AiPlayerWatch
            w = db.get(AiPlayerWatch, to_user)
            prev = int((w.flags or {}).get("flirt_heat", 0)) if w is not None else 0
            heat = ADULT.heat_of(text, prev)
            reply = ADULT.reply(_rng, text, target.gender if target else None, heat)
            kind, source = "flirt", "template"
            if w is not None:
                fl = dict(w.flags or {})
                fl["flirt_heat"] = heat
                fl["flirt_unanswered"] = 0
                w.flags = fl
            # LLM only for light flirt; explicit stays on varied templates (safer and more consistent)
            if heat == 0:
                s_ = SP.SECTION.get(db)
                if int(s_["intelligence"]) >= 5 and s_.get("llm_enabled"):
                    from ...ai import llm as LLM
                    llm_text = LLM.reply(db, persona, text, s_, to_user=to_user, adult=True)
                    if llm_text and ADULT.safe(llm_text):
                        reply, source = llm_text, "llm"
        else:
            reply, kind, source = ADULT.deflect(_rng), "flirt_deflect", "template"
        from ..chat import dm_channel
        _say(db, persona, channel or dm_channel(ai_uid, to_user), reply)
        remember(db, persona, to_user, "Флиртовали в личке" if kind == "flirt" else "Отшутился от флирта")
        log(db, persona, "reply", to=to_user, intent=kind, source=source)
        return True
    if text == "__welcome__":
        kind, reply = "welcome_dm", DLG.line(_rng, "welcome_dm", persona.style, ctx)
        source = "template"
    else:
        if recall(db, persona, to_user):
            ctx["name"] = ctx["name"] + ", снова"
        kind, reply = DLG.reply(_rng, text, persona.style, ctx)
        reply, source = SP.compose(db, _rng, persona, reply, to_user=to_user, user_text=text, kind=kind)
    from ..chat import dm_channel
    _say(db, persona, channel or dm_channel(ai_uid, to_user), reply)
    remember(db, persona, to_user, f"Говорили: {kind}")
    from ...ai import personality as PERS
    from ...ai import social as SOC
    PERS.evolve(db, persona, "chat")
    SOC.relate(db, persona.user_id, to_user, "dm")
    log(db, persona, "reply", to=to_user, intent=kind, source=source)
    return True


def handle_mention(db: Session, channel: str, user_id: str, text: str) -> bool:
    """In public channels at most one persona answers, only sometimes, with a cooldown."""
    from ...ai import speech as SP
    kind = DLG.intent(text)
    if kind == "unknown" or _rng.random() > AI()["reply_chance"] * SP.frequency(db) or not _chat_allowed(db):
        return False
    persona = _pick_speaker(db, channel)
    if persona is None:
        return False
    base = DLG.line(_rng, kind, persona.style, _context(db, persona, user_id))
    from . import banter
    banter.say_reply(db, persona, channel, SP.compose(db, _rng, persona, base, to_user=user_id, user_text=text,
                                                      kind=kind, public=True)[0])  # paced like the chat
    log(db, persona, "chat_reply", channel=channel, intent=kind)
    return True


def process_replies(db: Session, budget: int) -> int:
    """Legacy path (AI Director off or not alive): consume due dm/mention events from the database queue."""
    from ...ai import events as EV
    from .control import global_switches
    chat_on = global_switches(db).get("chat", True)
    done = 0
    for ev in EV.due(db, max(1, budget) * 3, ("dm", "mention")):
        if done >= budget:
            break
        EV.mark(ev)
        if not chat_on:
            continue  # chat switched off: events are consumed without answers
        pl = ev.payload or {}
        try:
            with db.begin_nested():
                if ev.kind == "dm":
                    ok = handle_dm(db, ev.persona_user_id or "", pl.get("to_user", ""), pl.get("channel"), pl.get("text", ""))
                else:
                    ok = handle_mention(db, pl.get("channel", "global"), pl.get("user_id", ""), pl.get("text", ""))
        except Exception as e:  # a broken event must not block the queue
            ok = False
            ev.payload = {**pl, "error": str(e)[:120]}
        done += int(bool(ok))
    db.flush()
    return done


def _chat_allowed(db: Session) -> bool:
    """Public-channel reply rate limit, persisted (works across processes): per hour and with a short cooldown."""
    since = utcnow() - timedelta(hours=1)
    recent = db.scalars(select(AiActivityLog.created_at).where(AiActivityLog.activity == "chat_reply",
                                                               AiActivityLog.created_at >= since)
                        .order_by(AiActivityLog.id.desc()).limit(AI()["chat_global_per_hour"])).all()
    if len(recent) >= AI()["chat_global_per_hour"]:
        return False
    return not recent or (utcnow() - as_utc(recent[0])).total_seconds() >= AI()["chat_cooldown_s"] / 4


def _pick_speaker(db: Session, channel: str) -> AiPersona | None:
    from .. import channels as CHN
    if not CHN.ai_may_post(db, channel):
        return None
    ids = CHN.ai_member_ids(db, channel)
    if ids is not None:
        cands = db.scalars(select(AiPersona).where(AiPersona.user_id.in_(ids), AiPersona.active.is_(True)).limit(80)).all()
    elif channel.startswith("region:"):
        code = channel.split(":", 1)[1]
        cands = [p for p in db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).limit(200)) if CHN.ai_region(p) == code]
    else:
        cands = db.scalars(select(AiPersona).where(AiPersona.active.is_(True)).limit(80)).all()
    cands = [c for c in cands if _awake(c)] or cands
    talk = [c for c in cands if (c.temperament or {}).get("talkative", 0.5) > 0.4] or cands
    return _rng.choice(talk) if talk else None


# ------------------------------------------------------------------ behavior scheduler & activity simulator
def _awake(p: AiPersona) -> bool:
    now = utcnow()
    sch = p.schedule or {}
    if sch.get("weekend_only") and now.weekday() < 5:
        return False
    hours = sch.get("hours") or list(range(24))
    return now.hour in hours


def tick(db: Session) -> dict:
    """One scheduler step: bounded number of persona actions + queued replies."""
    now = utcnow()
    limit = AI()["max_actions_per_tick"]
    stats = {"actions": 0, "replies": process_replies(db, max(2, limit // 3))}
    from . import banter
    stats["chat"] = banter.keep_alive(db, AI())  # AI-to-AI conversations keep the chat alive
    stats["reactions"] = banter.react_sometimes(db)
    due = db.scalars(select(AiPersona).where(AiPersona.active.is_(True), AiPersona.next_action_at <= now)
                     .order_by(AiPersona.next_action_at).limit(limit * 3)).all()
    for persona in due:
        if stats["actions"] >= limit:
            break
        if persona.day != day():
            persona.day, persona.actions_today = day(), 0
        prof = db.get(PlayerProfile, persona.user_id)
        if not _awake(persona) or persona.actions_today >= AI()["max_actions_per_persona_day"]:
            persona.next_action_at = now + timedelta(minutes=_rng.randint(30, 120))
            continue
        prof.last_seen_at = now  # simulated presence follows the persona's own schedule
        act = _choose(persona)
        try:
            with db.begin_nested():
                ACTIONS[act](db, persona, prof)
        except Exception as e:  # one failing persona must not stop the tick
            log(db, persona, "error", action=act, error=str(e)[:120])
        persona.actions_today += 1
        persona.last_action_at = now
        talk = (persona.temperament or {}).get("talkative", 0.5)
        persona.next_action_at = now + timedelta(minutes=_rng.randint(8, 50) / max(0.3, talk))
        stats["actions"] += 1
    _trim(db)
    db.flush()
    return stats


def _choose(persona: AiPersona) -> str:
    weights = {"level": 3, "chat": 2, "arena": 3, "guild": 3, "friend": 1, "raid": 3, "event": 1, "war": 1}
    for i in persona.interests or []:
        if i in weights:
            weights[i] += 3
    talk = (persona.temperament or {}).get("talkative", 0.5)
    weights["chat"] = int(weights["chat"] * (0.5 + talk))
    from ...ai import personality as PERS
    weights = PERS.action_weights(persona, weights)  # traits, ambitions, habits and mood (stage 2)
    keys = list(weights)
    return _rng.choices(keys, weights=[weights[k] for k in keys])[0]


def act_level(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Believable progression: slow growth with a soft cap by account age; updates power and arena defense."""
    from ...ai import tiers as TR
    if persona.tier in TR.TIERS:  # stage 4: tier range, own pace, adapted to the real world's level
        cap = TR.level_cap(db, persona.tier)
        pace = max(0.2, persona.pace or 1.0)
    else:
        age_days = max(1, (utcnow() - as_utc(prof.created_at)).days)
        cap = min(D.LEVEL_CAP_MVP, 10 + age_days // 2 + (15 if persona.archetype == "veteran" else 0))
        pace = 1.0
    heroes = db.scalars(select(PlayerHero).where(PlayerHero.user_id == persona.user_id).order_by(PlayerHero.level)).all()
    if heroes and heroes[0].level < cap and _rng.random() < min(0.95, 0.6 * pace):
        heroes[0].level += 1
    if prof.level < cap and _rng.random() < min(0.9, 0.25 * pace):
        prof.level += 1
        _maybe_promote(db, persona, prof)
    compute_power(db, persona.user_id)
    ap = db.get(ArenaProfile, persona.user_id)
    if ap:
        sq = freeze_squad(db, persona.user_id)
        ap.defense, ap.defense_power = sq, squad_power(sq)
    log(db, persona, "level", level=prof.level)


def _maybe_promote(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """A persona that outgrew its tier moves up (rarely, by its own pace): biography, memory, personality."""
    from ...ai import memory as MEM
    from ...ai import personality as PERS
    from ...ai import tiers as TR
    nxt = TR.next_tier(persona.tier or "")
    if nxt is None or prof.level < TR.tier_range(nxt)[0] + 2 or _rng.random() > 0.3:
        return
    persona.tier = nxt
    persona.pace = round(TR.TIERS[nxt]["pace"] * _rng.uniform(0.85, 1.15), 2)
    text = f"Стал игроком уровня «{TR.TIERS[nxt]['name']}» (уровень {prof.level})"
    MEM.add(db, persona, "goal", text, importance=3)
    MEM.bio_add(db, persona, "tier", text)
    PERS.evolve(db, persona, "tier_up")
    log(db, persona, "tier_up", tier=nxt)


def act_chat(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    from . import banter, control
    from ...ai import speech as SP
    if not control.allowed(db, "chat"):
        return
    if _rng.random() > SP.frequency(db):
        return
    if banter.ai_messages_last_hour(db) >= AI().get("chat_ai_per_hour", 45):
        return
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    channel = "global"
    if m and _rng.random() < 0.4:
        humans = db.scalar(select(func.count()).select_from(GuildMember).join(PlayerProfile, PlayerProfile.user_id == GuildMember.user_id)
                           .where(GuildMember.guild_id == m.guild_id, PlayerProfile.is_ai.is_(False))) or 0
        if humans:  # talk in a guild chat only where real players can read it
            channel = f"guild:{m.guild_id}"
    text = banter.ambient(db, persona, channel)
    if not text:
        return  # the channel is quiet after a discussion
    from ...ai import personality as PERS
    PERS.evolve(db, persona, "chat")
    log(db, persona, "chat", channel=channel, text=text[:60])


def act_arena(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """AI ladder matches, and (when allowed) training attacks on real players' defenses so defense history
    stays lively. Real ratings change only if the owner enabled "arena_rated"."""
    from . import control
    me = db.get(ArenaProfile, persona.user_id)
    if me is None or not me.defense:
        return
    from ...ai import compete as COMP
    if not COMP.arena_allowed(db, persona):
        return  # daily arena limit for AI (stage 10, admin setting)
    from ..arena import current_season, elo
    season = current_season(db)
    vs_real = control.allowed(db, "arena") and _rng.random() < 0.5
    target = None
    if vs_real:
        cands = db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(False), ArenaProfile.defense_power > 0)
                           .order_by(func.abs(ArenaProfile.defense_power - me.defense_power)).limit(20)).all()
        today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        for c in cands:
            p = db.get(PlayerProfile, c.user_id)
            from .control import player_prefs
            if not player_prefs(p).get("arena_defense", True):
                continue
            hits = db.scalar(select(func.count()).select_from(ArenaMatch).join(PlayerProfile, PlayerProfile.user_id == ArenaMatch.attacker_id)
                             .where(ArenaMatch.defender_id == c.user_id, ArenaMatch.created_at >= today,
                                    PlayerProfile.is_ai.is_(True))) or 0
            if hits < 5:
                target = c
                break
    if target is None:
        target = _revenge_target(db, persona, me)
    if target is None:
        opp = db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(True), ArenaProfile.user_id != me.user_id,
                                                    ArenaProfile.defense_power > 0)
                         .order_by(func.abs(ArenaProfile.rating - me.rating)).limit(10)).all()
        if not opp:
            return
        target = COMP.pick_opponent(db, persona, me, list(opp), _rng)  # analyses opponents (stage 10)
    seed = secrets.randbits(40)
    sim = pvp(db, me.defense, target.defense, seed)
    won = sim["result"] == "victory"
    d_att = elo(me.rating, target.rating, 1.0 if won else 0.0)
    rated = target.is_ai or control.global_switches(db).get("arena_rated", False)
    d_def = -round(d_att * 0.5) if rated else 0
    me.rating += d_att
    target.rating += d_def
    me.wins += won
    me.losses += not won
    if not target.is_ai:
        if won:
            target.def_losses += 1
        else:
            target.def_wins += 1
    db.add(ArenaMatch(season_id=season.id, kind="ranked" if rated and not target.is_ai else "training",
                      attacker_id=me.user_id, defender_id=target.user_id, result=sim["result"], delta_att=d_att,
                      delta_def=d_def, seed=seed, attacker_snapshot=me.defense, defender_snapshot=target.defense))
    _arena_experience(db, persona, target, won)
    log(db, persona, "arena", vs_real=not target.is_ai, won=won)


def _revenge_target(db: Session, persona: AiPersona, me: ArenaProfile) -> ArenaProfile | None:
    """Experience changes behaviour (stage 14): a hot-tempered persona or one with the "revenge" habit seeks a rematch
    with an AI rival that beat it. Real players are never chased for revenge."""
    from ...ai import memory as MEM
    t = persona.traits or {}
    if not ("revenge" in (persona.habits or []) or t.get("temper", 0) > 0.7) or _rng.random() > 0.5:
        return None
    for m in MEM.recall(db, persona, kinds=("defeat",), limit=5):
        if not m.subject_user_id:
            continue
        ap = db.get(ArenaProfile, m.subject_user_id)
        if ap is not None and ap.is_ai and ap.user_id != me.user_id and ap.defense_power > 0:
            return ap
    return None


def _arena_experience(db: Session, persona: AiPersona, target: ArenaProfile, won: bool) -> None:
    from ...ai import memory as MEM
    from ...ai import personality as PERS
    name = (db.get(PlayerProfile, target.user_id).nickname if db.get(PlayerProfile, target.user_id) else "соперник")
    from ...ai import social as SOC
    SOC.relate(db, persona.user_id, target.user_id, "arena_win" if won else "arena_loss")
    if target.is_ai:
        SOC.relate(db, target.user_id, persona.user_id, "arena_loss" if won else "arena_win")
    else:  # a training fight against a real player's defense: maybe a friendly rivalry message (stage 16)
        from ...ai import outreach as OUT
        OUT.after_arena(db, persona, target.user_id, won, _rng)
    if won:
        row = PERS.count(persona, "wins_row", reset=("losses_row",))
        total = PERS.count(persona, "arena_wins")
        MEM.add(db, persona, "victory", f"Победил {name} на арене", subject=target.user_id,
                importance=3 if row >= 5 else 1)
        if total % 25 == 0:
            MEM.bio_add(db, persona, "milestone", f"{total} побед на арене")
        PERS.evolve(db, persona, "arena_win")
    else:
        row = PERS.count(persona, "losses_row", reset=("wins_row",))
        PERS.count(persona, "arena_losses")
        MEM.add(db, persona, "defeat", f"Проиграл {name} на арене", subject=target.user_id,
                importance=2 if row >= 3 else 1)
        PERS.evolve(db, persona, "arena_loss")
        from ...ai import compete as COMP
        COMP.maybe_rebuild_defense(db, persona)
        lost_to = [m for m in MEM.recall(db, persona, subject=target.user_id, kinds=("defeat",), limit=5)]
        if len(lost_to) >= 3 and target.is_ai and not MEM.recall(db, persona, subject=target.user_id, kinds=("relationship",), limit=1):
            MEM.add(db, persona, "relationship", f"{name} — соперник на арене", subject=target.user_id, importance=2)
            PERS.evolve(db, persona, "conflict", note=f"соперничество с {name}")


def act_guild(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    from . import control
    from ..guilds import G, join, levels, member_count
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    if m is None:
        if "guild" not in (persona.interests or []) and _rng.random() < 0.6:
            return
        # real guilds that welcome AI recruits first (never more than a third of the roster), then AI guilds
        for g in db.scalars(select(Guild).where(Guild.join_mode == "open").order_by(func.random()).limit(10)):
            if g.is_ai or not control.allowed(db, "guild_help", g, "recruit"):
                continue
            n = member_count(db, g.id)
            ai_n = db.scalar(select(func.count()).select_from(GuildMember).join(PlayerProfile, PlayerProfile.user_id == GuildMember.user_id)
                             .where(GuildMember.guild_id == g.id, PlayerProfile.is_ai.is_(True))) or 0
            if n <= G()["max_members"] - 3 and (ai_n + 1) * 3 <= n + 1 and prof.level >= (g.min_level or 1):
                join(db, g, persona.user_id, None, "open")
                _guild_joined(db, persona, g)
                log(db, persona, "guild_join", guild=g.name)
                return
        g = db.scalar(select(Guild).where(Guild.is_ai.is_(True)).order_by(func.random()).limit(1))
        if g is not None and member_count(db, g.id) < G()["max_members"] - 3:
            db.add(GuildMember(guild_id=g.id, user_id=persona.user_id, role="novice", last_active_at=utcnow()))
            _guild_joined(db, persona, g)
            log(db, persona, "guild_join", guild=g.name)
        return
    m.last_active_at = utcnow()
    g = db.get(Guild, m.guild_id)
    policy = control.guild_policy(g)
    if not g.is_ai and not control.allowed(db, "guild_help"):
        return
    from ...ai import play as PLAY
    if PLAY.SECTION.get(db)["progression"] != "rules" or g.is_ai:
        # legacy / AI guilds: virtual daily activity (an AI guild's treasury is its own; real guilds get real
        # donations only — under the rules the AI donates gold it earned, see app/ai/play.py)
        g.treasury = (g.treasury or 0) + _rng.randint(20, 80)
        m.contribution_week = (m.contribution_week or 0) + 5
        g.week_points = (g.week_points or 0) + 5
    manage = m.role in ("leader", "deputy", "officer") and (g.is_ai or policy.get("management"))
    if manage:
        for a in db.scalars(select(GuildApplication).where(GuildApplication.guild_id == g.id, GuildApplication.status == "pending",
                                                           GuildApplication.kind == "application")):
            if ai_guild_review(db, g, a.user_id):
                a.status = "accepted"
                join(db, g, a.user_id, persona.user_id, "approval")
        lv = levels(db, g.id)
        for code, b in sorted(G()["buildings"].items(), key=lambda kv: kv[1]["cost"][min(len(kv[1]["cost"]) - 1, lv.get(kv[0], 1 if kv[0] == "hall" else 0))]):
            cur = lv.get(code, 1 if code == "hall" else 0)
            if cur < b["max"] and b["cost"][cur] <= (g.treasury or 0) and all(
                    lv.get(r, 1 if r == "hall" else 0) >= n for r, n in (b.get("requires") or {}).items()):
                g.treasury -= b["cost"][cur]
                row = db.get(GuildUpgrade, (g.id, code))
                if row is None:
                    row = GuildUpgrade(guild_id=g.id, code=code, kind="building", level=cur)
                    db.add(row)
                row.level = cur + 1
                from ..guilds import log as glog
                glog(db, g.id, persona.user_id, "building", None, code=code, level=cur + 1, ai=True)
                break
    act_war(db, persona, prof)
    from ...ai import personality as PERS
    PERS.evolve(db, persona, "guild_help")
    log(db, persona, "guild_activity", guild=g.name)


def _guild_joined(db: Session, persona: AiPersona, g: Guild) -> None:
    from ...ai import memory as MEM
    from ...ai import personality as PERS
    from ...ai import social as SOC
    for mate in db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == g.id, GuildMember.user_id != persona.user_id)
                           .limit(5)):
        SOC.mutual(db, persona.user_id, mate, "guild_mate")
    MEM.add(db, persona, "decision", f"Вступил в гильдию «{g.name}»", importance=3)
    MEM.bio_add(db, persona, "guild", f"Вступил в гильдию «{g.name}»")
    PERS.evolve(db, persona, "guild_join")


def act_war(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """AI members fight in guild wars (AI guilds always; real guilds only if the leader allows it)."""
    from . import control
    from ...models import GuildWar
    from sqlalchemy import or_
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    if m is None:
        return
    g = db.get(Guild, m.guild_id)
    if not control.allowed(db, "guild_wars", g, "wars"):
        return
    w = db.scalar(select(GuildWar).where(GuildWar.status == "active", or_(GuildWar.guild_a == g.id, GuildWar.guild_b == g.id)))
    if w is None:
        return
    other = w.guild_b if w.guild_a == g.id else w.guild_a
    targets = [x.user_id for x in db.scalars(select(GuildMember).where(GuildMember.guild_id == other))]
    if not targets:
        return
    from ..guilds import do_war_attack
    from ...core.errors import GameError
    try:
        r = do_war_attack(db, persona.user_id, _rng.choice(targets))
        log(db, persona, "war_attack", points=r["points"])
    except GameError:
        pass


def act_friend(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Accept requests; sometimes send a daily gift to a real friend (within the normal daily limits)."""
    for r in db.scalars(select(FriendRequest).where(FriendRequest.to_id == persona.user_id, FriendRequest.status == "pending")):
        from ..friends import make_friends
        r.status = "accepted"
        make_friends(db, persona.user_id, r.from_id, r.source)
        remember(db, persona, r.from_id, "Подружились", kind="relationship")
        from ...ai import personality as PERS
        from ...ai import social as SOC
        PERS.evolve(db, persona, "friend")
        SOC.mutual(db, persona.user_id, r.from_id, "friend")
    friends = list(db.scalars(select(Friendship.friend_id).where(Friendship.user_id == persona.user_id)))
    real = [f for f in friends if not db.get(PlayerProfile, f).is_ai]
    if real and (persona.temperament or {}).get("helpful", 0.5) > _rng.random():
        to = _rng.choice(real)
        if not db.scalar(select(FriendGift).where(FriendGift.from_id == persona.user_id, FriendGift.to_id == to,
                                                  FriendGift.day == day(), FriendGift.kind == "gift")):
            db.add(FriendGift(from_id=persona.user_id, to_id=to, day=day(), kind="gift",
                              contents=dict(cfg()["friends"]["gift_contents"])))
            from ...ai import personality as PERS
            from ...ai import social as SOC
            PERS.evolve(db, persona, "gift")
            SOC.relate(db, persona.user_id, to, "gift")
            log(db, persona, "gift", to=to)


def act_raid(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """AI help with bosses: own guild boss (AI guild, or real guild that allows it) and shared world/seasonal bosses.
    Fair-play limits: AI get no rewards, never land the final blow and stop below 10% HP, so players finish the boss."""
    from . import control
    if not control.allowed(db, "raids"):
        return
    from ...models import RaidAttack
    from ..raids import boss_conf, current_instance, fight
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    options = [("world", None), ("seasonal", None)]
    if m:
        g = db.get(Guild, m.guild_id)
        if g.is_ai or control.guild_policy(g).get("raids"):
            options.insert(0, ("guild", m.guild_id))
    kind, scope = _rng.choice(options)
    inst = current_instance(db, kind, scope)
    if inst.status != "active" or inst.hp_left <= inst.hp_max * 0.10:
        return
    if db.scalar(select(func.count()).select_from(RaidAttack).where(RaidAttack.raid_id == inst.id,
                                                                    RaidAttack.user_id == persona.user_id)) >= 3:
        return  # same attempt budget as a player
    b = boss_conf(inst.boss_code)
    sim, dmg, pidx, _ = fight(db, persona.user_id, b, inst.boss_code, inst.hp_left, inst.hp_max, inst.stage, secrets.randbits(40))
    real_guild = scope and not db.get(Guild, scope).is_ai
    if kind != "guild" or real_guild:
        dmg = max(0, min(dmg, inst.hp_left - int(inst.hp_max * 0.10)))
    inst.hp_left = max(0, inst.hp_left - dmg)
    db.add(RaidAttack(raid_id=inst.id, user_id=persona.user_id, damage=dmg, phase=pidx, seed=0, team_snapshot=[]))
    if inst.hp_left <= 0:  # only possible for a purely virtual guild boss
        inst.status, inst.loot_done = "defeated", True
    from ...ai import personality as PERS
    PERS.evolve(db, persona, "raid")
    if m is not None:
        from ...ai import social as SOC
        mate = db.scalar(select(GuildMember.user_id).where(GuildMember.guild_id == m.guild_id,
                                                           GuildMember.user_id != persona.user_id).order_by(func.random()).limit(1))
        if mate:
            SOC.relate(db, persona.user_id, mate, "raid_together")
    log(db, persona, "raid", kind=kind, damage=dmg)


def act_event(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Personas react to world events in chat but never add progress."""
    from ...ai import personality as PERS
    if db.scalar(select(WorldEvent).where(WorldEvent.status == "active")) is not None:
        PERS.evolve(db, persona, "event")
        from ...ai import compete as COMP
        pts = COMP.contribute_event(db, persona)  # separate "AI residents' contribution", capped (D-05)
        if pts:
            log(db, persona, "event_contribution", points=pts)
    if _rng.random() < 0.5:
        act_chat(db, persona, prof)


ACTIONS = {"level": act_level, "chat": act_chat, "arena": act_arena, "guild": act_guild, "friend": act_friend,
           "raid": act_raid, "event": act_event, "war": act_war}


def _trim(db: Session) -> None:
    """Decision D-06: nothing is deleted after 7 days any more — old rows move to the long-term archive in batches."""
    if _rng.random() < 0.05:
        from ...ai import memory as MEM
        MEM.archive(db)


def overview(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(AiPersona)) or 0
    active = db.scalar(select(func.count()).select_from(AiPersona).where(AiPersona.active.is_(True))) or 0
    by_arch = dict(db.execute(select(AiPersona.archetype, func.count()).group_by(AiPersona.archetype)).all())
    last = [{"activity": a.activity, "payload": a.payload, "at": as_utc(a.created_at).isoformat()}
            for a in db.scalars(select(AiActivityLog).order_by(AiActivityLog.id.desc()).limit(30))]
    return {"total": total, "active": active, "target": target_population(db), "by_archetype": by_arch,
            "ai_guilds": db.scalar(select(func.count()).select_from(Guild).where(Guild.is_ai.is_(True))) or 0,
            "queued_replies": __import__("app.ai.events", fromlist=["pending"]).pending(db), "recent": last, "limits": AI()}
