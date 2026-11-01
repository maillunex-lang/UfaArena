"""Guild AI (stage 9): AI personas found their own guilds, recruit, assign roles, elect leaders, keep traditions and
reputation, make alliances (D-12) and fight in conflicts. Guilds keep their history and live on without real players.

Safety: elections, role changes and war declarations happen only in AI guilds (`is_ai`); real guilds' leadership is
never touched; real players in AI guilds keep their roles. Wars declared by AI are only AI-vs-AI."""
from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, utcnow
from ..models import (
    AiGuildState, AiPersona, Guild, GuildMember, GuildUpgrade, GuildWar, PlayerProfile,
)
from .sections import Section

SECTION = Section(
    "ai_guilds",
    {"max_ai_guilds": 8, "found_min_free": 10, "election_days": 14, "diplomacy": True, "ai_wars": True,
     "war_cooldown_h": 48, "traditions": True, "welcome_newcomers": True},
    {"max_ai_guilds": ("int", 0, 50), "found_min_free": ("int", 4, 200), "election_days": ("int", 1, 90),
     "diplomacy": ("bool",), "ai_wars": ("bool",), "war_cooldown_h": ("int", 6, 720), "traditions": ("bool",),
     "welcome_newcomers": ("bool",)},
    {"max_ai_guilds": "ИИ-гильдий максимум", "found_min_free": "ИИ без гильдии, чтобы основать новую",
     "election_days": "Выборы лидера в ИИ-гильдиях каждые, дней", "diplomacy": "Дипломатия и союзы ИИ-гильдий",
     "ai_wars": "ИИ-гильдии объявляют войны (только друг другу)", "war_cooldown_h": "Перерыв между войнами ИИ-гильдии, часов",
     "traditions": "Традиции гильдий", "welcome_newcomers": "ИИ приветствуют новичков в гильдии"})

TRADITIONS = {
    "sunday_raid": "По воскресеньям — общий поход на босса",
    "welcome": "Каждого новичка встречают в чате",
    "donations": "Каждый день — вклад в казну",
    "arena_night": "Вечер арены: соревнуемся, кто выше",
    "mentors": "Опытные помогают новичкам советом",
    "story_club": "Вместе проходим сюжет и обсуждаем легенды",
}
NAME_A = ["Стражи", "Дети", "Беркуты", "Волки", "Хранители", "Сыны", "Тени", "Всадники", "Лучники", "Огни"]
NAME_B = ["Иремеля", "Ямантау", "Агидели", "Шульган-Таша", "Нугуша", "Зилаира", "Торатау", "Курая", "Урала", "Акбузата"]


def state(db: Session, g: Guild, rng: random.Random | None = None) -> AiGuildState:
    st = db.get(AiGuildState, g.id)
    if st is None:
        rng = rng or random.Random(g.id)
        trad = rng.sample(list(TRADITIONS), 2) if g.is_ai else []
        st = AiGuildState(guild_id=g.id, reputation=0.0, traditions=trad, relations={}, history=[],
                          next_election_at=utcnow() + timedelta(days=rng.randint(3, 14)) if g.is_ai else None,
                          updated_at=utcnow())
        db.add(st)
        db.flush()
    return st


def _hist(st: AiGuildState, kind: str, text: str, **extra) -> None:
    st.history = (list(st.history or []) + [{"at": utcnow().isoformat(), "kind": kind, "text": text[:200], **extra}])[-100:]
    st.updated_at = utcnow()


def _ai_members(db: Session, gid: str) -> list[tuple[GuildMember, AiPersona]]:
    rows = db.execute(select(GuildMember, AiPersona).join(AiPersona, AiPersona.user_id == GuildMember.user_id)
                      .where(GuildMember.guild_id == gid)).all()
    return [(m, p) for m, p in rows]


def reputation(db: Session, g: Guild) -> float:
    """0…100 from size, level, war wins and the average reputation of members among AI residents."""
    from . import social as SOC
    n = db.scalar(select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == g.id)) or 0
    wins = db.scalar(select(func.count()).select_from(GuildWar).where(GuildWar.winner == g.id)) or 0
    ids = list(db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == g.id).limit(30)))
    soc = sum(SOC.reputation(db, u) for u in ids) / max(1, len(ids))
    return round(max(0.0, min(100.0, n * 2 + (g.level or 1) * 4 + wins * 5 + soc * 30)), 1)


# ------------------------------------------------------------------ alliances (answers to proposals, D-12)
def relation(db: Session, a: Guild, b: Guild) -> float:
    st = state(db, a)
    return float((st.relations or {}).get(b.id, 0.0))


def consider_alliance(db: Session, ai_guild: Guild, other: Guild, rng: random.Random | None = None) -> bool:
    if not SECTION.get(db)["diplomacy"]:
        return False
    rng = rng or random.Random()
    rel = relation(db, ai_guild, other)
    leader = db.scalar(select(AiPersona).where(AiPersona.user_id == ai_guild.leader_id))
    t = (leader.traits or {}) if leader else {}
    chance = 0.35 + rel * 0.5 + (t.get("loyalty", 0.5) - 0.5) * 0.3 + (t.get("sociability", 0.5) - 0.5) * 0.2
    chance += min(0.2, reputation(db, other) / 500)
    ok = rng.random() < max(0.05, min(0.95, chance))
    st = state(db, ai_guild)
    _hist(st, "alliance_answer", f"{'Принято' if ok else 'Отклонено'} предложение союза от «{other.name}»")
    return ok


# ------------------------------------------------------------------ founding, roles, elections
def found_guild(db: Session, rng: random.Random, s: dict) -> Guild | None:
    have = db.scalar(select(func.count()).select_from(Guild).where(Guild.is_ai.is_(True))) or 0
    if have >= s["max_ai_guilds"]:
        return None
    in_guild = select(GuildMember.user_id)
    free = list(db.scalars(select(AiPersona).where(AiPersona.active.is_(True), AiPersona.user_id.not_in(in_guild)).limit(200)))
    if len(free) < s["found_min_free"]:
        return None
    def score(p: AiPersona) -> float:
        t = p.traits or {}
        prof = db.get(PlayerProfile, p.user_id)
        return t.get("ambition", 0.5) + t.get("loyalty", 0.5) + (prof.level if prof else 1) / 80
    founder = max(free, key=score)
    name = None
    for _ in range(20):
        cand = f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}"
        if not db.scalar(select(Guild.id).where(Guild.name == cand)):
            name = cand
            break
    if name is None:
        return None
    tag = "".join(w[0] for w in name.split())[:2].upper() + str(rng.randint(10, 99))
    g = Guild(name=name[:32], tag=tag[:5], description="ИИ-гильдия: её основали ИИ-жители. Новички приветствуются!",
              join_mode="approval", min_level=1, leader_id=founder.user_id, is_ai=True,
              specialization=rng.choice(["warriors", "hunters", "keepers"]), treasury=rng.randint(200, 1200))
    db.add(g)
    db.flush()
    db.add(GuildUpgrade(guild_id=g.id, code="hall", kind="building", level=1))
    from . import social as SOC
    friends = [r.object_id for r in SOC.best_friends(db, founder.user_id, limit=8)]
    pool = [p for p in free if p.id != founder.id]
    pool.sort(key=lambda p: (p.user_id not in friends, rng.random()))
    recruits = pool[:rng.randint(4, 8)]
    db.add(GuildMember(guild_id=g.id, user_id=founder.user_id, role="leader", last_active_at=utcnow()))
    for i, p in enumerate(recruits):
        db.add(GuildMember(guild_id=g.id, user_id=p.user_id, role="deputy" if i == 0 else "member", last_active_at=utcnow()))
    db.flush()
    st = state(db, g, rng)
    _hist(st, "founded", f"Гильдию основал ИИ-житель, первые участники: {len(recruits) + 1}")
    from . import memory as MEM
    MEM.add(db, founder, "decision", f"Основал гильдию «{g.name}»", importance=4)
    MEM.bio_add(db, founder, "guild", f"Основал гильдию «{g.name}»")
    for p in recruits:
        MEM.bio_add(db, p, "guild", f"Вступил в новую гильдию «{g.name}»")
    from ..social.guilds import log as glog
    glog(db, g.id, founder.user_id, "founded", None, ai=True)
    return g


def assign_roles(db: Session, g: Guild) -> int:
    """AI leader appoints a deputy and officers among AI members by contribution and trust. Real members untouched."""
    from . import social as SOC
    rows = [(m, p) for m, p in _ai_members(db, g.id) if m.user_id != g.leader_id]
    if not rows:
        return 0
    def score(mp):
        m, p = mp
        r = SOC.get(db, g.leader_id, m.user_id, create=False) if g.leader_id else None
        return (m.contribution_week or 0) + 40 * (r.trust if r else 0) + 20 * (p.traits or {}).get("loyalty", 0.5)
    rows.sort(key=score, reverse=True)
    want = {0: "deputy", 1: "officer", 2: "officer"}
    changed = 0
    for i, (m, p) in enumerate(rows):
        role = want.get(i, "veteran" if i < 6 else "member")
        if m.role != role and m.role != "leader":
            m.role = role
            changed += 1
    return changed


def run_election(db: Session, g: Guild, rng: random.Random, s: dict) -> dict | None:
    from . import social as SOC
    st = state(db, g, rng)
    if st.next_election_at and as_utc(st.next_election_at) > utcnow():
        return None
    members = _ai_members(db, g.id)
    st.next_election_at = utcnow() + timedelta(days=int(s["election_days"]))
    if len(members) < 3:
        return None
    def merit(mp):
        m, p = mp
        prof = db.get(PlayerProfile, p.user_id)
        t = p.traits or {}
        return (m.contribution_week or 0) + 50 * t.get("loyalty", 0.5) + 30 * t.get("ambition", 0.5) + \
            30 * SOC.reputation(db, p.user_id) + (prof.level if prof else 1) / 2
    cands = sorted(members, key=merit, reverse=True)[:3]
    votes = {p.user_id: 0 for _, p in cands}
    for m, voter in members:
        best, best_v = None, -9.0
        for _, c in cands:
            r = SOC.get(db, voter.user_id, c.user_id, create=False)
            v = (r.sympathy + r.trust if r else 0.0) + rng.uniform(0, 0.4) + (0.6 if c.user_id == voter.user_id else 0)
            if v > best_v:
                best, best_v = c.user_id, v
        votes[best] += 1
        if best != voter.user_id:
            SOC.relate(db, voter.user_id, best, "vote")
    winner = max(votes, key=lambda k: (votes[k], k == g.leader_id))
    names = {p.user_id: db.get(PlayerProfile, p.user_id).nickname for _, p in cands}
    tally = ", ".join(f"{names[k]} — {v}" for k, v in sorted(votes.items(), key=lambda kv: -kv[1]))
    old = g.leader_id
    from ..social.chat import system_message
    from ..social.guilds import log as glog
    from . import memory as MEM
    if winner != old:
        for m, p in members:
            if m.user_id == winner:
                m.role = "leader"
            elif m.user_id == old:
                m.role = "deputy"
        g.leader_id = winner
        wp = db.scalar(select(AiPersona).where(AiPersona.user_id == winner))
        MEM.add(db, wp, "goal", f"Избран лидером гильдии «{g.name}»", importance=4)
        MEM.bio_add(db, wp, "guild", f"Избран лидером гильдии «{g.name}»")
        text = f"🗳 Выборы лидера: побеждает {names[winner]} ({tally})."
    else:
        text = f"🗳 Выборы лидера: {names[winner]} остаётся лидером ({tally})."
    system_message(db, f"guild:{g.id}", text + " Голосовали ИИ-жители гильдии.")
    glog(db, g.id, None, "election", winner, votes=votes)
    _hist(st, "election", text)
    return {"winner": winner, "votes": votes}


# ------------------------------------------------------------------ diplomacy and conflicts (AI guilds)
def _update_relations(db: Session, g: Guild, others: list[Guild]) -> None:
    from ..models import AiRelationship
    st = state(db, g)
    ids = list(db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == g.id).limit(30)))
    rel = dict(st.relations or {})
    for o in others:
        oids = list(db.scalars(select(GuildMember.user_id).where(GuildMember.guild_id == o.id).limit(30)))
        if not ids or not oids:
            continue
        row = db.execute(select(func.avg(AiRelationship.sympathy - AiRelationship.dislike))
                         .where(AiRelationship.subject_id.in_(ids), AiRelationship.object_id.in_(oids))).scalar()
        base = float(row or 0.0)
        rel[o.id] = round(max(-1.0, min(1.0, 0.7 * float(rel.get(o.id, 0.0)) + 0.3 * base)), 3)
    st.relations = rel


def _settle_finished_wars(db: Session, g: Guild) -> None:
    st = state(db, g)
    done = {h.get("war") for h in (st.history or []) if h.get("kind") == "war_end"}
    since = utcnow() - timedelta(days=3)
    for w in db.scalars(select(GuildWar).where(GuildWar.status == "finished", GuildWar.ends_at >= since,
                                               (GuildWar.guild_a == g.id) | (GuildWar.guild_b == g.id))):
        if w.id in done:
            continue
        other = w.guild_b if w.guild_a == g.id else w.guild_a
        rel = dict(st.relations or {})
        rel[other] = round(max(-1.0, float(rel.get(other, 0.0)) - (0.25 if w.winner == other else 0.1)), 3)
        st.relations = rel
        on = db.get(Guild, other)
        res = "победа" if w.winner == g.id else ("ничья" if w.winner is None else "поражение")
        _hist(st, "war_end", f"Война с «{on.name if on else '?'}»: {res}", war=w.id)


def diplomacy(db: Session, g: Guild, rng: random.Random, s: dict) -> dict:
    from ..social import alliances as AL
    out = {}
    others = [o for o in db.scalars(select(Guild).where(Guild.id != g.id, Guild.is_ai.is_(True)).limit(20))]
    _update_relations(db, g, others)
    _settle_finished_wars(db, g)
    st = state(db, g)
    if s["diplomacy"] and AL.alliance_of(db, g.id) is None and rng.random() < 0.2:
        friends = sorted((o for o in others if (st.relations or {}).get(o.id, 0) > 0.3), key=lambda o: -st.relations[o.id])
        for o in friends:
            try:
                if consider_alliance(db, o, g, rng):
                    a = AL.form(db, g, o, g.leader_id)
                    _hist(st, "alliance", f"Заключён союз «{a.name}» с «{o.name}»")
                    _hist(state(db, o), "alliance", f"Заключён союз «{a.name}» с «{g.name}»")
                    out["alliance"] = a.name
                    break
            except Exception:  # alliance rules (full, already allied, at war) -> try another time
                continue
    if s["ai_wars"] and rng.random() < 0.15:
        busy = set()
        for w in db.scalars(select(GuildWar).where(GuildWar.status == "active")):
            busy |= {w.guild_a, w.guild_b}
        last = max((as_utc(w.ends_at) for w in db.scalars(select(GuildWar).where(
            (GuildWar.guild_a == g.id) | (GuildWar.guild_b == g.id)))), default=None)  # end of the latest war
        cooldown_ok = last is None or utcnow() - last > timedelta(hours=int(s["war_cooldown_h"]))
        allies = set(AL.allies(db, g.id))
        foes = [o for o in others if (st.relations or {}).get(o.id, 0) < -0.3 and o.id not in busy and o.id not in allies]
        if g.id not in busy and cooldown_ok and foes:
            from ..social.guilds import G, log as glog, member_count
            o = min(foes, key=lambda x: st.relations[x.id])
            if member_count(db, g.id) >= G()["war"]["min_members"] and member_count(db, o.id) >= G()["war"]["min_members"]:
                w = GuildWar(guild_a=g.id, guild_b=o.id, ends_at=utcnow() + timedelta(hours=G()["war"]["hours"]))
                db.add(w)
                glog(db, g.id, g.leader_id, "war_start", None, opponent=o.name, ai=True)
                glog(db, o.id, None, "war_declared", None, opponent=g.name)
                _hist(st, "war", f"Объявлена война гильдии «{o.name}»")
                out["war"] = o.name
    return out


def welcome(db: Session, g: Guild, newcomer_id: str) -> bool:
    """Tradition "welcome": an AI member greets a real newcomer in the guild chat (paced like the rest of the chat)."""
    if not SECTION.get(db)["welcome_newcomers"]:
        return False
    prof = db.get(PlayerProfile, newcomer_id)
    if prof is None or prof.is_ai:
        return False
    st = db.get(AiGuildState, g.id)
    if not g.is_ai and (st is None or "welcome" not in (st.traditions or [])):
        return False
    rows = [p for m, p in _ai_members(db, g.id) if (p.traits or {}).get("sociability", 0.5) > 0.4] or \
        [p for m, p in _ai_members(db, g.id)]
    if not rows:
        return False
    from ..social.ai import banter
    from ..social.channels import ai_may_post
    if not ai_may_post(db, f"guild:{g.id}"):
        return False
    rng = random.Random()
    p = rng.choice(rows)
    lines = [f"{prof.nickname}, добро пожаловать в «{g.name}»! 🙌", f"О, новенький! Привет, {prof.nickname}, располагайся 🙂",
             f"{prof.nickname}, рады тебе! Если что — спрашивай в чате.", f"Салам, {prof.nickname}! У нас дружно, заходи на босса."]
    banter.say_reply(db, p, f"guild:{g.id}", rng.choice(lines))
    from . import social as SOC
    SOC.relate(db, p.user_id, newcomer_id, "chat")
    return True


def run(db: Session, rng: random.Random, limit: int = 4) -> dict:
    s = SECTION.get(db)
    out: dict = {"founded": None, "elections": 0, "roles": 0, "diplomacy": []}
    if rng.random() < 0.1:
        g = found_guild(db, rng, s)
        out["founded"] = g.name if g else None
    guilds = list(db.scalars(select(Guild).where(Guild.is_ai.is_(True)).order_by(func.random()).limit(limit)))
    for g in guilds:
        st = state(db, g, rng)
        st.reputation = reputation(db, g)
        out["roles"] += assign_roles(db, g)
        if run_election(db, g, rng, s):
            out["elections"] += 1
        d = diplomacy(db, g, rng, s)
        if d:
            out["diplomacy"].append({g.name: d})
    db.flush()
    return out
