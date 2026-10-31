"""Tournaments: weekly and monthly templates; individual, team (3 players) and guild entries; formats
points (Swiss pairing), groups -> final bracket, single-elimination bracket; special rules (rarity cap,
single faction, random battle condition). All rounds are computed by the server on schedule from squads
frozen at registration. Rewards are resources and cosmetics only — no combat advantages."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..models import GuildMember, PlayerProfile, SeasonResult, Tournament, TournamentEntry, TournamentMatch
from . import progression as P
from .common import card, cfg, check_rules, freeze_squad, notify, pvp, squad_power

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def T() -> dict:
    return cfg()["tournaments"]


# ------------------------------------------------------------------ schedule
def period_start(scale: str, now: datetime) -> tuple[datetime, str]:
    if scale == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        y, w, _ = start.isocalendar()
        return start, f"{y}-W{w:02d}"
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, start.strftime("%Y-%m")


def rounds_total(t: Tournament, n_entries: int) -> int:
    tpl = T()["templates"][t.template]
    if t.format == "points":
        return int(tpl.get("fights", 5))
    size = 1
    while size < max(2, n_entries):
        size *= 2
    bracket_rounds = size.bit_length() - 1
    if t.format == "groups":
        return 3 + max(1, bracket_rounds - 1)
    return bracket_rounds


def ensure(db: Session, now: datetime | None = None) -> list[Tournament]:
    now = now or utcnow()
    out = []
    for code, tpl in T()["templates"].items():
        cur, _ = period_start(tpl["scale"], now)
        nxt = cur + timedelta(days=7) if tpl["scale"] == "weekly" else (cur + timedelta(days=32)).replace(day=1)
        for start, key in (period_start(tpl["scale"], cur), period_start(tpl["scale"], nxt)):
            out.append(_ensure_one(db, code, tpl, start, key))
    return [t for t in out if t is not None]


def _ensure_one(db: Session, code: str, tpl: dict, start: datetime, key: str) -> Tournament:
    """Registration is open from creation until `reg_ends_at`; the next period is created in advance,
    so there is always a tournament of each template open for registration."""
    tcode = f"{code}:{key}"
    t = db.scalar(select(Tournament).where(Tournament.code == tcode))
    if t is None:
        rules = dict(tpl.get("rules", {}))
        if rules.pop("random_condition", False):
            conds = T()["conditions"]
            h = int(hashlib.sha256(tcode.encode()).hexdigest(), 16)
            rules["condition"] = conds[h % len(conds)]
        reg_end = start + timedelta(hours=tpl["reg_hours"])
        t = Tournament(code=tcode, template=code, name=tpl["name"], kind=tpl["kind"], format=tpl["format"],
                       rules=rules, status="registration", reg_ends_at=reg_end,
                       ends_at=reg_end + timedelta(hours=tpl["run_hours"]))
        db.add(t)
        db.flush()
    return t


# ------------------------------------------------------------------ entries
def _squads_for(db: Session, t: Tournament, owner: str, members: list[str]) -> list[list[dict]]:
    squads = []
    for uid in members:
        try:
            sq = freeze_squad(db, uid)
        except GameError:
            continue
        check_rules(sq, t.rules)
        squads.append(sq)
    return squads


class RegisterIn(BaseModel):
    teammates: list[str] = Field(default_factory=list, max_length=2)
    squad: list[str | None] | None = Field(default=None, min_length=5, max_length=5)


@router.post("/{tid}/register")
def register(tid: str, body: RegisterIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    t = db.get(Tournament, tid, with_for_update=True)
    if t is None:
        raise GameError("not_found", "Турнир не найден", 404)
    if t.status != "registration" or as_utc(t.reg_ends_at) <= utcnow():
        raise GameError("closed", "Регистрация закрыта", 409)
    tpl = T()["templates"][t.template]
    p = db.get(PlayerProfile, user.id)
    owner, members, name, guild_id = user.id, [user.id], p.nickname, None
    if t.kind == "team":
        from .friends import are_friends
        mates = list(dict.fromkeys(body.teammates))
        if len(mates) != int(tpl.get("team_size", 3)) - 1:
            raise GameError("team_size", "В команде должно быть 3 игрока: вы и два друга")
        for m in mates:
            if not are_friends(db, user.id, m):
                raise GameError("not_friends", "В команду можно позвать только друзей", 403)
            if db.get(PlayerProfile, m).is_ai:
                raise GameError("no_ai", "ИИ-персонажи не участвуют в командных турнирах игроков", 400)
        members = [user.id] + mates
        name = f"Команда {p.nickname}"
    elif t.kind == "guild":
        from .guilds import can, membership
        m = membership(db, user.id)
        if m is None or not can(m.role, "war"):
            raise GameError("forbidden", "Гильдию регистрирует глава или заместитель", 403)
        from .guilds import members as gmembers
        from ..models import Guild
        g = db.get(Guild, m.guild_id)
        owner, guild_id, name = g.id, g.id, f"[{g.tag}] {g.name}"
        members = [x.user_id for x in gmembers(db, g.id)]
    taken = set()
    for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)):
        taken |= set(e.members)
        if e.owner_id == owner:
            raise GameError("already", "Уже зарегистрировано", 409)
    if taken & set(members):
        raise GameError("already", "Кто-то из участников уже зарегистрирован в этом турнире", 409)
    if body.squad and t.kind == "individual":
        sq = freeze_squad(db, user.id, body.squad)
        check_rules(sq, t.rules)
        squads = [sq]
    else:
        squads = _squads_for(db, t, owner, members)
    if not squads:
        raise GameError("no_squad", "Нет отряда, подходящего под правила турнира")
    if t.kind == "guild":
        squads = sorted(squads, key=squad_power, reverse=True)[:5]
    e = TournamentEntry(tournament_id=t.id, owner_id=owner, guild_id=guild_id, name=name, members=members,
                        snapshot=squads)
    db.add(e)
    db.flush()
    for uid in members:
        if not db.get(PlayerProfile, uid).is_ai:
            P.on(db, uid, "tournament_join", ref=t.id)
            if uid != user.id:
                notify(db, uid, f"Вы в турнире «{t.name}»", f"{p.nickname} зарегистрировал вас. Отряд зафиксирован.")
    db.commit()
    return entry_view(db, e)


@router.post("/{tid}/withdraw")
def withdraw(tid: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    t = db.get(Tournament, tid)
    if t is None or t.status != "registration":
        raise GameError("closed", "Сняться можно только до старта", 409)
    for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)):
        if user.id == e.owner_id or (e.guild_id is None and user.id in e.members and e.owner_id == user.id):
            db.delete(e)
            db.commit()
            return {"ok": True}
    raise GameError("not_found", "Регистрация не найдена", 404)


# ------------------------------------------------------------------ battles
def _cond(t: Tournament) -> dict | None:
    c = t.rules.get("condition")
    return {c["stat"]: c["mult"]} if c else None


def duel(db: Session, t: Tournament, a: TournamentEntry, b: TournamentEntry, seed: int) -> tuple[str, dict]:
    """Entries with several squads play squad-vs-squad by power order; majority wins (ties -> higher total power)."""
    sa = sorted(a.snapshot, key=squad_power, reverse=True)
    sb = sorted(b.snapshot, key=squad_power, reverse=True)
    n = min(len(sa), len(sb))
    wins_a = wins_b = 0
    games = []
    for i in range(n):
        sim = pvp(db, sa[i], sb[i], seed + i, _cond(t))
        won = sim["result"] == "victory"
        wins_a += won
        wins_b += not won
        games.append({"seed": seed + i, "a_won": won, "duration": sim["duration"]})
    if wins_a == wins_b:
        winner = a.id if sum(map(squad_power, sa)) >= sum(map(squad_power, sb)) else b.id
    else:
        winner = a.id if wins_a > wins_b else b.id
    return winner, {"games": games, "score": [wins_a, wins_b]}


def _record(db: Session, t: Tournament, rnd: int, stage: str, a: TournamentEntry, b: TournamentEntry | None) -> None:
    if b is None:  # bye
        a.points += T()["points_win"]
        a.wins += 1
        db.add(TournamentMatch(tournament_id=t.id, round=rnd, stage=stage, a_entry=a.id, b_entry=None,
                               winner_entry=a.id, summary={"bye": True}))
        return
    seed = secrets.randbits(40)
    winner, smry = duel(db, t, a, b, seed)
    for e in (a, b):
        if e.id == winner:
            e.points += T()["points_win"]
            e.wins += 1
        else:
            e.points += T()["points_loss"]
            e.losses += 1
            if stage == "bracket":
                e.eliminated = True
    db.add(TournamentMatch(tournament_id=t.id, round=rnd, stage=stage, a_entry=a.id, b_entry=b.id,
                           winner_entry=winner, seed=seed, summary=smry))


def _fill_ai(db: Session, t: Tournament) -> None:
    """Individual brackets/groups may be topped up with labelled AI entries so the format can run."""
    if t.kind != "individual" or t.format == "points":
        return
    entries = db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)).all()
    need = int(T()["ai_fill_to"]) - len(entries)
    if need <= 0:
        return
    taken = {m for e in entries for m in e.members}
    for p in db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True), PlayerProfile.user_id.notin_(taken))
                        .order_by(PlayerProfile.level.desc()).limit(need * 2)):
        if need <= 0:
            break
        try:
            sq = freeze_squad(db, p.user_id)
            check_rules(sq, t.rules)
        except GameError:
            continue
        db.add(TournamentEntry(tournament_id=t.id, owner_id=p.user_id, name=p.nickname, members=[p.user_id],
                               snapshot=[sq], is_ai=True))
        need -= 1
    db.flush()


def play_round(db: Session, t: Tournament) -> None:
    entries = db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)).all()
    rnd = t.current_round + 1
    if t.format == "points":
        order = sorted(entries, key=lambda e: (-e.points, -e.wins, e.id))
        played = {(m.a_entry, m.b_entry) for m in db.scalars(select(TournamentMatch).where(TournamentMatch.tournament_id == t.id))}
        pool = list(order)
        while pool:
            a = pool.pop(0)
            idx = next((i for i, b in enumerate(pool) if (a.id, b.id) not in played and (b.id, a.id) not in played), 0 if pool else None)
            b = pool.pop(idx) if idx is not None and pool else None
            _record(db, t, rnd, "points", a, b)
    elif t.format == "groups" and rnd <= 3:
        if rnd == 1:
            ordered = sorted(entries, key=lambda e: -sum(map(squad_power, e.snapshot)))
            for i, e in enumerate(ordered):  # snake seeding into groups of 4
                e.group_no = (i % max(1, len(ordered) // 4)) + 1
        groups: dict[int, list] = {}
        for e in entries:
            groups.setdefault(e.group_no, []).append(e)
        for g in groups.values():
            g.sort(key=lambda e: e.id)
            pairs = [(0, 1), (2, 3)] if rnd == 1 else ([(0, 2), (1, 3)] if rnd == 2 else [(0, 3), (1, 2)])
            for i, j in pairs:
                if i < len(g) and j < len(g):
                    _record(db, t, rnd, "group", g[i], g[j])
                elif i < len(g) and j >= len(g) and len(g) % 2:
                    _record(db, t, rnd, "group", g[i], None)
        if rnd == 3:  # top-2 of each group advance to the bracket
            for g in groups.values():
                g.sort(key=lambda e: (-e.points, -e.wins))
                for k, e in enumerate(g):
                    e.eliminated = k >= 2
    else:
        alive = sorted([e for e in entries if not e.eliminated], key=lambda e: (-e.points, -sum(map(squad_power, e.snapshot))))
        while len(alive) > 1:
            a, b = alive.pop(0), alive.pop(-1)
            _record(db, t, rnd, "bracket", a, b)
        if alive:
            _record(db, t, rnd, "bracket", alive[0], None)
    t.current_round = rnd
    db.flush()


def standings(db: Session, t: Tournament) -> list[TournamentEntry]:
    entries = db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)).all()
    if t.format in ("bracket", "groups"):
        last_round = {}
        for m in db.scalars(select(TournamentMatch).where(TournamentMatch.tournament_id == t.id, TournamentMatch.stage == "bracket")):
            for e in (m.a_entry, m.b_entry):
                if e:
                    last_round[e] = max(last_round.get(e, 0), m.round + (1 if m.winner_entry == e else 0))
        return sorted(entries, key=lambda e: (-last_round.get(e.id, 0), -e.points, -e.wins))
    return sorted(entries, key=lambda e: (-e.points, -e.wins, e.losses))


def finish(db: Session, t: Tournament) -> None:
    if t.status == "finished":
        return
    ranked = standings(db, t)
    rw = T()["rewards"]
    results = []
    place = 0
    for e in ranked:
        place += 1
        results.append({"place": place, "name": e.name, "is_ai": e.is_ai, "points": e.points, "wins": e.wins})
        if e.is_ai:
            continue  # AI entries are listed for transparency and never receive rewards
        reward = rw.get(str(place)) or (rw["top10"] if place <= 10 else rw["participant"])
        for uid in e.members:
            if db.get(PlayerProfile, uid) is None or db.get(PlayerProfile, uid).is_ai:
                continue
            r = dict(reward)
            if t.kind != "individual" and "cosmetic" in r and uid != (e.owner_id if t.kind == "team" else uid):
                pass
            notify(db, uid, f"Турнир «{t.name}» завершён", f"«{e.name}»: место {place} из {len(ranked)}.", r)
            if not db.scalar(select(SeasonResult).where(SeasonResult.user_id == uid, SeasonResult.category == "tournament",
                                                        SeasonResult.ref == t.code[:64])):
                db.add(SeasonResult(user_id=uid, category="tournament", season_id=0, ref=t.code[:64],
                                    result={"name": t.name, "place": place, "of": len(ranked), "entry": e.name}))
    t.status = "finished"
    t.results = {"standings": results[:32]}
    from .chat import system_message
    if results:
        system_message(db, "global", f"Турнир «{t.name}» завершён. Победитель: {results[0]['name']}"
                       + (" (ИИ)" if results[0]["is_ai"] else "") + ".")
    db.flush()


def advance(db: Session, now: datetime | None = None) -> int:
    """Scheduler step: open new periods, start tournaments after registration, play due rounds, finish."""
    now = now or utcnow()
    ensure(db, now)
    n = 0
    for t in db.scalars(select(Tournament).where(Tournament.status.in_(("registration", "running")))).all():
        if t.status == "registration" and as_utc(t.reg_ends_at) <= now:
            _fill_ai(db, t)
            cnt = len(db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)).all())
            if cnt < 2:
                t.status = "finished"
                t.results = {"cancelled": True, "reason": "Недостаточно участников"}
                continue
            t.status = "running"
        if t.status != "running":
            continue
        cnt = len(db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)).all())
        total = rounds_total(t, cnt)
        span = (as_utc(t.ends_at) - as_utc(t.reg_ends_at)) / max(1, total)
        while t.current_round < total and now >= as_utc(t.reg_ends_at) + span * t.current_round:
            alive = [e for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)) if not e.eliminated]
            if t.format != "points" and t.current_round >= (3 if t.format == "groups" else 0) and len(alive) <= 1:
                break
            play_round(db, t)
            n += 1
        alive = [e for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)) if not e.eliminated]
        if now >= as_utc(t.ends_at) or t.current_round >= total or (t.format == "bracket" and len(alive) <= 1):
            finish(db, t)
    db.flush()
    return n


# ------------------------------------------------------------------ views
def entry_view(db: Session, e: TournamentEntry) -> dict:
    return {"id": e.id, "name": e.name, "is_ai": e.is_ai, "points": e.points, "wins": e.wins, "losses": e.losses,
            "eliminated": e.eliminated, "group": e.group_no, "members": len(e.members),
            "power": sum(map(squad_power, e.snapshot))}


def tournament_view(db: Session, t: Tournament, user_id: str, full: bool = False) -> dict:
    mine = None
    for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)):
        if user_id in e.members:
            mine = entry_view(db, e)
    tpl = T()["templates"][t.template]
    cnt = len(db.scalars(select(TournamentEntry.id).where(TournamentEntry.tournament_id == t.id)).all())
    out = {"id": t.id, "name": t.name, "kind": t.kind, "format": t.format, "scale": tpl["scale"], "status": t.status,
           "rules": t.rules, "reg_ends_at": as_utc(t.reg_ends_at).isoformat(), "ends_at": as_utc(t.ends_at).isoformat(),
           "round": t.current_round, "rounds": rounds_total(t, cnt), "entries": cnt, "mine": mine,
           "rewards": T()["rewards"], "team_size": tpl.get("team_size"), "results": t.results}
    if full:
        out["standings"] = [entry_view(db, e) for e in standings(db, t)][:64]
        names = {e.id: e.name for e in db.scalars(select(TournamentEntry).where(TournamentEntry.tournament_id == t.id))}
        out["matches"] = [{"id": m.id, "round": m.round, "stage": m.stage, "a": names.get(m.a_entry, "?"),
                           "b": names.get(m.b_entry, "—") if m.b_entry else "—", "winner": names.get(m.winner_entry, "?"),
                           "score": m.summary.get("score"), "bye": m.summary.get("bye", False)}
                          for m in db.scalars(select(TournamentMatch).where(TournamentMatch.tournament_id == t.id)
                                              .order_by(TournamentMatch.round.desc()).limit(80))]
    return out


@router.get("")
def tournaments(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    advance(db)
    db.commit()
    cur = db.scalars(select(Tournament).where(Tournament.status != "finished").order_by(Tournament.reg_ends_at)).all()
    past = db.scalars(select(Tournament).where(Tournament.status == "finished").order_by(Tournament.ends_at.desc()).limit(6)).all()
    return {"current": [tournament_view(db, t, user.id) for t in cur], "past": [tournament_view(db, t, user.id) for t in past],
            "conditions": T()["conditions"]}


@router.get("/{tid}")
def tournament(tid: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    t = db.get(Tournament, tid)
    if t is None:
        raise GameError("not_found", "Турнир не найден", 404)
    return tournament_view(db, t, user.id, full=True)


@router.get("/match/{mid}/replay")
def match_replay(mid: str, game: int = 0, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    m = db.get(TournamentMatch, mid)
    if m is None or not m.b_entry:
        raise GameError("not_found", "Бой не найден", 404)
    t = db.get(Tournament, m.tournament_id)
    a, b = db.get(TournamentEntry, m.a_entry), db.get(TournamentEntry, m.b_entry)
    sa = sorted(a.snapshot, key=squad_power, reverse=True)
    sb = sorted(b.snapshot, key=squad_power, reverse=True)
    game = max(0, min(game, min(len(sa), len(sb)) - 1))
    return {"simulation": pvp(db, sa[game], sb[game], m.seed + game, _cond(t)), "a": a.name, "b": b.name}


_ = (GuildMember, card)
