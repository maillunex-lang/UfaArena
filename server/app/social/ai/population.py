"""AI Population Engine: population_manager, persona_registry, behavior_scheduler, dialogue (see dialogue.py),
memory_store, activity_simulator, guild_ai_controller, matchmaking_adapter (separate AI ladder) and audit log.

Rules: every persona is flagged is_ai and labelled in the UI; personas never buy, never touch real rankings,
never add to real event progress, never attack shared real raid bosses; total actions per tick and per day
are capped to protect the server."""
from __future__ import annotations

import random
import secrets
from collections import deque
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.db import as_utc, utcnow
from ...game import data as D
from ...models import (
    AiActivityLog, AiMemory, AiPersona, ArenaMatch, ArenaProfile, ChatMessage, FortressBuilding, Formation,
    FriendGift, FriendRequest, Friendship, Guild, GuildApplication, GuildMember, GuildUpgrade, PlayerHero,
    PlayerProfile, RaidInstance, Tournament, User, WorldEvent,
)
from ..common import cfg, compute_power, day, freeze_squad, league_of, pvp, squad_power
from . import dialogue as DLG
from . import personas as PR

_rng = random.Random()
_reply_queue: deque = deque(maxlen=200)   # (persona_user_id, to_user_id, channel, text, due_monotonic)
_mention_queue: deque = deque(maxlen=100)  # (channel, user_id, text)
_chat_times: deque = deque(maxlen=200)


def AI() -> dict:
    return cfg()["ai"]


def log(db: Session, persona: AiPersona, activity: str, **payload) -> None:
    db.add(AiActivityLog(persona_id=persona.id, activity=activity, payload=payload))


# ------------------------------------------------------------------ persona registry
def _summonable() -> list[dict]:
    return [h for h in D.HEROES if h.get("summonable", True) and not h.get("is_enemy")]


def create_persona(db: Session, rng: random.Random | None = None) -> AiPersona:
    rng = rng or _rng
    spec = PR.make(rng)
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
    pool = _summonable()
    n_heroes = min(len(pool), rng.randint(6, 14))
    picks = rng.sample(pool, n_heroes)
    weights = sorted(picks, key=lambda h: -h["rarity"])
    ids = []
    for h in weights:
        lv = max(1, min(D.LEVEL_CAP_MVP, spec["level"] + rng.randint(-6, 3)))
        ph = PlayerHero(user_id=u.id, hero_code=h["code"], level=lv, stars=rng.choice([0, 0, 0, 1, 1, 2]) if h["rarity"] <= 4 else 0)
        db.add(ph)
        db.flush()
        ids.append((ph.id, h))
    tanks = [i for i, h in ids if h["class_code"] in ("guardian", "warrior")][:2]
    rest = [i for i, h in ids if i not in tanks]
    slots = (tanks + rest)[:5]
    db.add(Formation(user_id=u.id, kind="campaign", slots=(slots + [None] * 5)[:5]))
    for code in D.BUILDINGS:
        db.add(FortressBuilding(user_id=u.id, code=code, level=max(1, min(10, spec["level"] // 6 + rng.randint(0, 2)))))
    persona = AiPersona(user_id=u.id, archetype=spec["archetype"], temperament=spec["temperament"],
                        backstory=spec["backstory"], style=spec["style"], schedule=spec["schedule"],
                        interests=spec["interests"], next_action_at=utcnow() + timedelta(seconds=rng.randint(20, 600)),
                        day=day())
    db.add(persona)
    db.flush()
    compute_power(db, u.id)
    spec_sq = freeze_squad(db, u.id)
    db.add(ArenaProfile(user_id=u.id, rating=1000 + rng.randint(-150, 250), defense=spec_sq,
                        defense_power=squad_power(spec_sq), is_ai=True, day=day()))
    log(db, persona, "created", archetype=spec["archetype"], style=spec["style"])
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
    retired = 0
    if len(active) > target:
        for p in active[target:]:
            p.active = False
            retired += 1
    db.flush()
    ensure_ai_guilds(db)
    return {"target": target, "active": len(active) + created - retired, "created": created, "retired": retired}


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
        remember(db, persona, from_user, "Подружились")
        queue_reply(ai_user_id, from_user, None, "__welcome__")
    return ok


# ------------------------------------------------------------------ memory store
def remember(db: Session, persona: AiPersona, subject: str, fact: str) -> None:
    db.add(AiMemory(persona_id=persona.id, subject_user_id=subject, fact=fact[:200],
                    expires_at=utcnow() + timedelta(days=30)))


def recall(db: Session, persona: AiPersona, subject: str) -> list[str]:
    return [m.fact for m in db.scalars(select(AiMemory).where(AiMemory.persona_id == persona.id,
                                                              AiMemory.subject_user_id == subject)
                                        .order_by(AiMemory.id.desc()).limit(5))]


# ------------------------------------------------------------------ reply queues (filled by chat)
def queue_reply(ai_user_id: str, to_user: str, channel: str | None, text: str) -> None:
    import time
    _reply_queue.append((ai_user_id, to_user, channel, text, time.monotonic() + _rng.uniform(5, 40)))


def queue_mention(channel: str, user_id: str, text: str) -> None:
    _mention_queue.append((channel, user_id, text))


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


def process_replies(db: Session, budget: int) -> int:
    import time
    now = time.monotonic()
    done = 0
    keep = deque()
    while _reply_queue and done < budget:
        item = _reply_queue.popleft()
        ai_uid, to_user, channel, text, due = item
        if due > now:
            keep.append(item)
            continue
        persona = db.scalar(select(AiPersona).where(AiPersona.user_id == ai_uid))
        if persona is None:
            continue
        ctx = _context(db, persona, to_user)
        if text == "__welcome__":
            kind, reply = "welcome_dm", DLG.line(_rng, "welcome_dm", persona.style, ctx)
        else:
            if recall(db, persona, to_user):
                ctx["name"] = ctx["name"] + ", снова"
            kind, reply = DLG.reply(_rng, text, persona.style, ctx)
        from ..chat import dm_channel
        _say(db, persona, channel or dm_channel(ai_uid, to_user), reply)
        remember(db, persona, to_user, f"Говорили: {kind}")
        log(db, persona, "reply", to=to_user, intent=kind)
        done += 1
    _reply_queue.extend(keep)
    # mentions in public channels: at most one persona answers, only sometimes, with a cooldown
    while _mention_queue and done < budget:
        channel, user_id, text = _mention_queue.popleft()
        kind = DLG.intent(text)
        if kind == "unknown" or _rng.random() > AI()["reply_chance"] or not _chat_allowed():
            continue
        persona = _pick_speaker(db, channel)
        if persona is None:
            continue
        _say(db, persona, channel, DLG.line(_rng, kind, persona.style, _context(db, persona, user_id)))
        _chat_times.append(time.monotonic())
        log(db, persona, "chat_reply", channel=channel, intent=kind)
        done += 1
    return done


def _chat_allowed() -> bool:
    import time
    now = time.monotonic()
    recent = [t for t in _chat_times if now - t < 3600]
    if len(recent) >= AI()["chat_global_per_hour"]:
        return False
    return not recent or now - recent[-1] >= AI()["chat_cooldown_s"] / 4


def _pick_speaker(db: Session, channel: str) -> AiPersona | None:
    if channel.startswith("guild:"):
        gid = channel.split(":", 1)[1]
        ids = [m.user_id for m in db.scalars(select(GuildMember).where(GuildMember.guild_id == gid))]
        cands = db.scalars(select(AiPersona).where(AiPersona.user_id.in_(ids), AiPersona.active.is_(True))).all()
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
    weights = {"level": 3, "chat": 2, "arena": 2, "guild": 2, "friend": 1, "raid": 1, "event": 1}
    for i in persona.interests or []:
        if i in weights:
            weights[i] += 3
    talk = (persona.temperament or {}).get("talkative", 0.5)
    weights["chat"] = int(weights["chat"] * (0.5 + talk))
    keys = list(weights)
    return _rng.choices(keys, weights=[weights[k] for k in keys])[0]


def act_level(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Believable progression: slow growth with a soft cap by account age; updates power and arena defense."""
    age_days = max(1, (utcnow() - as_utc(prof.created_at)).days)
    cap = min(D.LEVEL_CAP_MVP, 10 + age_days // 2 + (15 if persona.archetype == "veteran" else 0))
    heroes = db.scalars(select(PlayerHero).where(PlayerHero.user_id == persona.user_id).order_by(PlayerHero.level)).all()
    if heroes and heroes[0].level < cap and _rng.random() < 0.6:
        heroes[0].level += 1
    if prof.level < cap and _rng.random() < 0.25:
        prof.level += 1
    compute_power(db, persona.user_id)
    ap = db.get(ArenaProfile, persona.user_id)
    if ap:
        sq = freeze_squad(db, persona.user_id)
        ap.defense, ap.defense_power = sq, squad_power(sq)
    log(db, persona, "level", level=prof.level)


def act_chat(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    if not _chat_allowed():
        return
    import time
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    channel = "global"
    if m and _rng.random() < 0.5:
        humans = db.scalar(select(func.count()).select_from(GuildMember).join(PlayerProfile, PlayerProfile.user_id == GuildMember.user_id)
                           .where(GuildMember.guild_id == m.guild_id, PlayerProfile.is_ai.is_(False))) or 0
        if humans:  # talk in a guild chat only where real players can read it
            channel = f"guild:{m.guild_id}"
    topic = _rng.choice(["ambient", "ambient", "event", "raid", "hero", "arena", "tournament", "guild"])
    ctx = _context(db, persona)
    _say(db, persona, channel, DLG.line(_rng, topic, persona.style, ctx))
    _chat_times.append(time.monotonic())
    log(db, persona, "chat", channel=channel, topic=topic)


def act_arena(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """AI ladder only: AI vs AI training matches that never touch real ratings."""
    me = db.get(ArenaProfile, persona.user_id)
    if me is None or not me.defense:
        return
    opp = db.scalars(select(ArenaProfile).where(ArenaProfile.is_ai.is_(True), ArenaProfile.user_id != me.user_id,
                                                ArenaProfile.defense_power > 0)
                     .order_by(func.abs(ArenaProfile.rating - me.rating)).limit(5)).all()
    if not opp:
        return
    o = _rng.choice(opp)
    seed = secrets.randbits(40)
    sim = pvp(db, me.defense, o.defense, seed)
    won = sim["result"] == "victory"
    from ..arena import current_season, elo
    d = elo(me.rating, o.rating, 1.0 if won else 0.0)
    me.rating += d
    o.rating -= round(d * 0.5)
    me.wins += won
    me.losses += not won
    db.add(ArenaMatch(season_id=current_season(db).id, kind="training", attacker_id=me.user_id, defender_id=o.user_id,
                      result=sim["result"], delta_att=d, delta_def=-round(d * 0.5), seed=seed,
                      attacker_snapshot=me.defense, defender_snapshot=o.defense))
    log(db, persona, "arena_ai", won=won, delta=d)


def act_guild(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    if m is None:
        g = db.scalar(select(Guild).where(Guild.is_ai.is_(True)).order_by(func.random()).limit(1))
        if g is not None and "guild" in (persona.interests or []):
            from ..guilds import member_count, G
            if member_count(db, g.id) < G()["max_members"] - 3:  # leave room for real players
                db.add(GuildMember(guild_id=g.id, user_id=persona.user_id, role="novice", last_active_at=utcnow()))
                log(db, persona, "guild_join", guild=g.name)
        return
    m.last_active_at = utcnow()
    g = db.get(Guild, m.guild_id)
    if not g.is_ai:
        return  # in real guilds personas never spend or vote; they only chat and stay active
    g.treasury = (g.treasury or 0) + _rng.randint(20, 80)  # virtual guild economy, separate from real players
    m.contribution_week = (m.contribution_week or 0) + 5
    g.week_points = (g.week_points or 0) + 5
    if m.role in ("leader", "deputy", "officer"):
        for a in db.scalars(select(GuildApplication).where(GuildApplication.guild_id == g.id, GuildApplication.status == "pending",
                                                           GuildApplication.kind == "application")):
            from ..guilds import join
            if ai_guild_review(db, g, a.user_id):
                a.status = "accepted"
                join(db, g, a.user_id, persona.user_id, "approval")
        from ..guilds import G, levels
        lv = levels(db, g.id)
        for code, b in G()["buildings"].items():
            cur = lv.get(code, 1 if code == "hall" else 0)
            if cur < b["max"] and b["cost"][cur] <= (g.treasury or 0) and all(
                    lv.get(r, 1 if r == "hall" else 0) >= n for r, n in (b.get("requires") or {}).items()):
                g.treasury -= b["cost"][cur]
                row = db.get(GuildUpgrade, (g.id, code))
                if row is None:
                    row = GuildUpgrade(guild_id=g.id, code=code, kind="building", level=cur)
                    db.add(row)
                row.level = cur + 1
                log(db, persona, "guild_build", code=code, level=cur + 1)
                break
    log(db, persona, "guild_activity", guild=g.name)


def act_friend(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Accept requests; sometimes send a daily gift to a real friend (within the normal daily limits)."""
    for r in db.scalars(select(FriendRequest).where(FriendRequest.to_id == persona.user_id, FriendRequest.status == "pending")):
        from ..friends import make_friends
        r.status = "accepted"
        make_friends(db, persona.user_id, r.from_id, r.source)
    friends = list(db.scalars(select(Friendship.friend_id).where(Friendship.user_id == persona.user_id)))
    real = [f for f in friends if not db.get(PlayerProfile, f).is_ai]
    if real and (persona.temperament or {}).get("helpful", 0.5) > _rng.random():
        to = _rng.choice(real)
        if not db.scalar(select(FriendGift).where(FriendGift.from_id == persona.user_id, FriendGift.to_id == to,
                                                  FriendGift.day == day(), FriendGift.kind == "gift")):
            db.add(FriendGift(from_id=persona.user_id, to_id=to, day=day(), kind="gift",
                              contents=dict(cfg()["friends"]["gift_contents"])))
            log(db, persona, "gift", to=to)


def act_raid(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Personas only fight their own virtual guild's boss — never shared real raids."""
    m = db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id))
    if m is None or not db.get(Guild, m.guild_id).is_ai:
        return
    from ..raids import current_instance, fight, boss_conf
    inst = current_instance(db, "guild", m.guild_id)
    if inst.status != "active" or inst.hp_left <= 0:
        return
    b = boss_conf(inst.boss_code)
    sim, dmg, pidx, _ = fight(db, persona.user_id, b, inst.boss_code, inst.hp_left, inst.hp_max, inst.stage, secrets.randbits(40))
    inst.hp_left = max(0, inst.hp_left - dmg)
    from ...models import RaidAttack
    db.add(RaidAttack(raid_id=inst.id, user_id=persona.user_id, damage=dmg, phase=pidx, seed=0, team_snapshot=[]))
    if inst.hp_left <= 0:
        inst.status, inst.loot_done = "defeated", True  # virtual guild: no rewards are issued
    log(db, persona, "raid_ai_guild", damage=dmg)


def act_event(db: Session, persona: AiPersona, prof: PlayerProfile) -> None:
    """Personas react to world events in chat but never add progress."""
    if _rng.random() < 0.5:
        act_chat(db, persona, prof)


ACTIONS = {"level": act_level, "chat": act_chat, "arena": act_arena, "guild": act_guild, "friend": act_friend,
           "raid": act_raid, "event": act_event}


def _trim(db: Session) -> None:
    lim = utcnow() - timedelta(days=7)
    if _rng.random() < 0.05:
        db.query(AiActivityLog).filter(AiActivityLog.created_at < lim).delete(synchronize_session=False)
        db.query(AiMemory).filter(AiMemory.expires_at < utcnow()).delete(synchronize_session=False)


def overview(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(AiPersona)) or 0
    active = db.scalar(select(func.count()).select_from(AiPersona).where(AiPersona.active.is_(True))) or 0
    by_arch = dict(db.execute(select(AiPersona.archetype, func.count()).group_by(AiPersona.archetype)).all())
    last = [{"activity": a.activity, "payload": a.payload, "at": as_utc(a.created_at).isoformat()}
            for a in db.scalars(select(AiActivityLog).order_by(AiActivityLog.id.desc()).limit(30))]
    return {"total": total, "active": active, "target": target_population(db), "by_archetype": by_arch,
            "ai_guilds": db.scalar(select(func.count()).select_from(Guild).where(Guild.is_ai.is_(True))) or 0,
            "queued_replies": len(_reply_queue), "recent": last, "limits": AI()}
