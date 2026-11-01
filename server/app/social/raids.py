"""Raids and bosses: guild / world / seasonal / story (multi-stage) bosses with phases, vulnerabilities and
special conditions; asynchronous shared HP; co-op fights of up to 5 players; attempts that regenerate plus
tickets; transparent server-side loot rolls with history and duplicate protection."""
from __future__ import annotations

import random
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..game.battle_sim import hero_stats, make_unit
from ..models import (
    Guild, GuildMember, Hero, PlayerProfile, RaidAttack, RaidAttemptState, RaidInstance, RaidLobby, RaidLoot,
    SeasonResult,
)
from ..services import hero_dict, spend, wallet_dict
from . import progression as P
from .common import FACTION_ADV, card, cfg, freeze_squad, give, notify, run_battle, units_from_spec

router = APIRouter(prefix="/raids", tags=["raids"])
_rng = random.SystemRandom()  # loot rolls: OS entropy, never client-influenced


def R_() -> dict:
    return cfg()["raids"]


def boss_conf(code: str) -> dict:
    b = R_()["bosses"].get(code)
    if b is None:
        raise GameError("not_found", "Нет такого босса", 404)
    return b


def phase_of(b: dict, ratio: float) -> tuple[int, dict]:
    idx, ph = 0, b["phases"][0]
    for i, p in enumerate(b["phases"]):
        if ratio <= p["from"] + 1e-9:
            idx, ph = i, p
    return idx + 1, ph


# ------------------------------------------------------------------ attempts
def attempts(db: Session, user_id: str, kind: str, lock: bool = False) -> RaidAttemptState:
    conf = R_()["attempts"][kind]
    st = db.get(RaidAttemptState, (user_id, kind), with_for_update=lock)
    mx = max_attempts(db, user_id, kind)
    now = utcnow()
    if st is None:
        st = RaidAttemptState(user_id=user_id, kind=kind, attempts=float(mx), updated_at=now)
        db.add(st)
        db.flush()
        return st
    gained = (now - as_utc(st.updated_at)).total_seconds() / 3600 / conf["regen_hours"]
    if st.attempts < mx:
        st.attempts = min(float(mx), st.attempts + gained)
    st.updated_at = now
    return st


def max_attempts(db: Session, user_id: str, kind: str) -> int:
    mx = int(R_()["attempts"][kind]["max"])
    if kind == "guild":
        from .guilds import levels, membership
        m = membership(db, user_id)
        if m:
            mx += levels(db, m.guild_id).get("barracks", 0) // 2
    return mx


def next_attempt_in(st: RaidAttemptState, kind: str, mx: int) -> int | None:
    if st.attempts >= mx:
        return None
    frac = 1 - (st.attempts - int(st.attempts))
    return int(frac * R_()["attempts"][kind]["regen_hours"] * 3600)


def use_attempt(db: Session, user_id: str, kind: str, ticket: bool) -> str:
    st = attempts(db, user_id, kind, lock=True)
    if st.attempts >= 1:
        st.attempts -= 1
        return "attempt"
    if ticket:
        spend(db, user_id, {R_()["ticket_currency"]: 1}, "raid_ticket", kind)
        return "ticket"
    raise GameError("no_attempts", "Попытки закончились. Они восстанавливаются со временем, или используйте билет рейда", 409)


# ------------------------------------------------------------------ instances
def _scope(db: Session, user_id: str, kind: str) -> str | None:
    if kind == "guild":
        m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
        if m is None:
            raise GameError("no_guild", "Гильдейский босс доступен только участникам гильдии", 403)
        return m.guild_id
    if kind == "story":
        m = db.scalar(select(GuildMember).where(GuildMember.user_id == user_id))
        return m.guild_id if m else f"solo:{user_id}"
    return None


def boss_for_kind(kind: str) -> str:
    for code, b in R_()["bosses"].items():
        if b["kind"] == kind:
            return code
    raise GameError("not_found", "Нет босса этого типа", 404)


def current_instance(db: Session, kind: str, scope: str | None, create: bool = True, lock: bool = False) -> RaidInstance | None:
    stmt = select(RaidInstance).where(RaidInstance.kind == kind, RaidInstance.status == "active")
    stmt = stmt.where(RaidInstance.guild_id == scope) if scope else stmt.where(RaidInstance.guild_id.is_(None))
    inst = db.scalar(stmt.order_by(RaidInstance.starts_at.desc()).with_for_update() if lock else stmt.order_by(RaidInstance.starts_at.desc()))
    if inst is not None and as_utc(inst.ends_at) <= utcnow():
        finish(db, inst, expired=True)
        inst = None
    if inst is None and create:
        code = boss_for_kind(kind)
        b = boss_conf(code)
        stage = 1
        if kind == "story":  # continue the stage chain after a defeat
            last = db.scalar(select(RaidInstance).where(RaidInstance.kind == kind, RaidInstance.guild_id == scope)
                             .order_by(RaidInstance.starts_at.desc()))
            if last is not None and last.status == "defeated" and last.stage < int(b.get("stages", 1)):
                stage = last.stage + 1
        hp = int(b["hp"] * (float(b.get("stage_hp_mult", 1.0)) ** (stage - 1)))
        inst = RaidInstance(kind=kind, boss_code=code, guild_id=scope, stage=stage, hp_max=hp, hp_left=hp,
                            ends_at=utcnow() + timedelta(days=b["days"]))
        db.add(inst)
        db.flush()
    return inst


def instance_view(db: Session, inst: RaidInstance, user_id: str) -> dict:
    b = boss_conf(inst.boss_code)
    ratio = inst.hp_left / inst.hp_max if inst.hp_max else 0
    pidx, ph = phase_of(b, ratio)
    my = db.scalar(select(func.coalesce(func.sum(RaidAttack.damage), 0)).where(
        RaidAttack.raid_id == inst.id, RaidAttack.user_id == user_id)) or 0
    top = db.execute(select(RaidAttack.user_id, func.sum(RaidAttack.damage).label("d")).where(RaidAttack.raid_id == inst.id)
                     .group_by(RaidAttack.user_id).order_by(func.sum(RaidAttack.damage).desc()).limit(10)).all()
    participants = db.scalar(select(func.count(func.distinct(RaidAttack.user_id))).where(RaidAttack.raid_id == inst.id)) or 0
    st = attempts(db, user_id, inst.kind)
    mx = max_attempts(db, user_id, inst.kind)
    return {
        "id": inst.id, "kind": inst.kind, "boss_code": inst.boss_code, "name": b["name"], "desc": b["desc"],
        "level": b["level"], "stage": inst.stage, "stages": int(b.get("stages", 1)), "hp_max": inst.hp_max,
        "hp_left": inst.hp_left, "status": inst.status, "ends_at": as_utc(inst.ends_at).isoformat(),
        "phase": pidx, "phase_name": ph["name"], "phase_note": ph["note"],
        "phases": [{"from": p["from"], "name": p["name"], "note": p["note"]} for p in b["phases"]],
        "my_damage": int(my), "participants": participants,
        "top": [{"nickname": card(db, uid)["nickname"], "is_ai": card(db, uid)["is_ai"], "damage": int(d)} for uid, d in top],
        "attempts": int(st.attempts), "max_attempts": mx, "next_attempt_s": next_attempt_in(st, inst.kind, mx),
        "base_reward": b["base_reward"],
        "loot": [{"name": x["name"], "item": x["item"], "chance": x["chance"], "rare": x["rare"]} for x in b["loot"]],
        "battle_seconds": R_()["battle_seconds"],
    }


@router.get("")
def overview(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    out = []
    for kind in ("guild", "world", "seasonal", "story"):
        try:
            scope = _scope(db, user.id, kind)
        except GameError as e:
            out.append({"kind": kind, "locked": e.detail["message"]})
            continue
        inst = current_instance(db, kind, scope)
        out.append(instance_view(db, inst, user.id))
    tickets = wallet_dict(db, user.id).get(R_()["ticket_currency"], 0)
    db.commit()
    return {"raids": out, "tickets": tickets, "coop_bosses": R_()["coop_bosses"], "coop_max": R_()["coop_max_players"]}


# ------------------------------------------------------------------ boss battle
def boss_unit(db: Session, code: str, b: dict, ph: dict, hp: int, stage: int = 1):
    h = db.get(Hero, b["hero"])
    hd = hero_dict(h)
    lvl = int(b["level"]) + (stage - 1) * 5
    st = hero_stats(hd, lvl)
    st["atk"] = int(st["atk"] * ph.get("atk_mult", 1.0))
    st["def"] = int(st["def"] * ph.get("def_mult", 1.0))
    st["hp"] = int(hp)
    u = make_unit(1, 2, hd, st, lvl, None)
    u.skill_level = 1 + stage
    return u


def apply_phase_to_team(team: list, ph: dict, spec: list[dict], extra_atk: float) -> list[str]:
    notes = []
    classes = {u["class"] for u in spec}
    for u in team:
        mult = 1 + extra_atk
        if ph.get("vuln_class") and u.cls == ph["vuln_class"]:
            mult *= ph["vuln_mult"]
        if ph.get("vuln_faction") and u.faction == ph["vuln_faction"]:
            mult *= ph["vuln_mult"]
        u.atk = int(u.atk * mult)
    if ph.get("need_class"):
        if ph["need_class"] in classes:
            for u in team:
                u.max_hp = int(u.max_hp * (1 + ph["need_bonus_hp"]))
                u.hp = u.max_hp
            notes.append("Условие фазы выполнено: отряд усилен")
        else:
            notes.append("Условие фазы не выполнено")
    return notes


def fight(db: Session, user_id: str, b: dict, code: str, hp_left: int, hp_max: int, stage: int, seed: int,
          spec: list[dict] | None = None, side_slot_offset: int = 0) -> tuple[dict, int, int, list[dict]]:
    from .guilds import guild_bonuses
    ratio = hp_left / hp_max if hp_max else 0
    pidx, ph = phase_of(b, ratio)
    spec = spec or freeze_squad(db, user_id)
    team = units_from_spec(db, spec, 0)
    gb = guild_bonuses(db, user_id)
    notes = apply_phase_to_team(team, ph, spec, gb.get("boss_dmg_pct", 0))
    boss = boss_unit(db, code, b, ph, hp_left, stage)
    sim, s = run_battle(team, [boss], seed, max_time=R_()["battle_seconds"])
    dmg = max(0, hp_left - max(0, boss.hp))
    sim["boss_damage"] = dmg
    sim["phase"] = pidx
    sim["phase_notes"] = notes
    return sim, dmg, pidx, spec


class AttackIn(BaseModel):
    kind: str = Field(pattern="^(guild|world|seasonal|story)$")
    use_ticket: bool = False


@router.post("/attack")
def attack(body: AttackIn, user: CurrentUser = Depends(player), key: str = Depends(require_key),
           db: Session = Depends(get_db)):
    def do():
        scope = _scope(db, user.id, body.kind)
        inst = current_instance(db, body.kind, scope, lock=True)
        if inst.status != "active" or inst.hp_left <= 0:
            raise GameError("defeated", "Босс уже повержен", 409)
        how = use_attempt(db, user.id, body.kind, body.use_ticket)
        b = boss_conf(inst.boss_code)
        seed = secrets.randbits(48)
        sim, dmg, pidx, spec = fight(db, user.id, b, inst.boss_code, inst.hp_left, inst.hp_max, inst.stage, seed)
        dmg = min(dmg, inst.hp_left)
        inst.hp_left -= dmg
        db.add(RaidAttack(raid_id=inst.id, user_id=user.id, damage=dmg, phase=pidx, seed=seed,
                          team_snapshot=[{k: u[k] for k in ("hero_code", "level", "stars", "power")} for u in spec]))
        reward = give(db, user.id, b["base_reward"], "raid_attack", inst.id)
        P.on(db, user.id, "raid_attack", dmg, ref=inst.id)
        killed = False
        if inst.hp_left <= 0:
            inst.hp_left = 0
            finish(db, inst)
            killed = True
        return {"simulation": sim, "damage": dmg, "used": how, "reward": reward, "killed": killed,
                "raid": instance_view(db, inst, user.id), "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, f"raid_attack:{body.kind}", body.model_dump(), do)


def roll_loot(db: Session, raid_id: str, user_ids: list[str], b: dict, base: dict | None = None) -> dict[str, list]:
    """One base reward per participant + independent server rolls per loot entry. Unique (raid, user, slot)."""
    out: dict[str, list] = {}
    for uid in user_ids:
        got = []
        slots = [("base", base or b["base_reward"], 1.0, False, "Награда за участие")]
        slots += [(f"loot:{i}", x["item"], float(x["chance"]), bool(x["rare"]), x["name"]) for i, x in enumerate(b["loot"])]
        for slot, item, chance, rare, name in slots:
            if db.scalar(select(RaidLoot).where(RaidLoot.raid_id == raid_id, RaidLoot.user_id == uid, RaidLoot.slot == slot)):
                continue
            roll = _rng.random() if slot != "base" else None
            if roll is not None and roll >= chance:
                continue
            db.add(RaidLoot(raid_id=raid_id, user_id=uid, slot=slot, item={"name": name, **item}, rare=rare,
                            probability=chance, roll=roll))
            got.append({"name": name, "item": item, "rare": rare, "chance": chance})
        out[uid] = got
    db.flush()
    return out


def finish(db: Session, inst: RaidInstance, expired: bool = False) -> None:
    if inst.loot_done:
        return
    b = boss_conf(inst.boss_code)
    users = [u for u in db.scalars(select(func.distinct(RaidAttack.user_id)).where(RaidAttack.raid_id == inst.id))
             if not (db.get(PlayerProfile, u) and db.get(PlayerProfile, u).is_ai)]  # AI helpers get no rewards
    inst.status = "expired" if expired else "defeated"
    inst.defeated_at = None if expired else utcnow()
    inst.loot_done = True
    if expired:  # no kill: participation reward only (shown in advance in the raid card)
        for uid in users:
            notify(db, uid, f"Рейд «{b['name']}» завершён", "Босс не повержен. Награда за участие.", b["base_reward"])
        return
    loot = roll_loot(db, inst.id, users, b)
    for uid, items in loot.items():
        total: dict[str, int] = {}
        lines = []
        for it in items:
            for k, v in it["item"].items():
                total[k] = total.get(k, 0) + int(v)
            lines.append(("★ " if it["rare"] else "") + it["name"])
        notify(db, uid, f"Босс «{b['name']}» повержен!", "Добыча: " + ", ".join(lines), total)
        db.add(SeasonResult(
            user_id=uid, category="raid", season_id=0, ref=inst.id[:64],
            result={"boss": b["name"], "stage": inst.stage, "rare": [i["name"] for i in items if i["rare"]]}))
    from .chat import system_message
    if inst.guild_id and not inst.guild_id.startswith("solo:"):
        system_message(db, f"guild:{inst.guild_id}", f"Босс «{b['name']}» повержен! Добыча разослана по почте.")
    elif inst.kind == "world":
        system_message(db, "global", f"Мировой босс «{b['name']}» повержен общими усилиями сервера!")
    db.flush()


@router.get("/loot")
def loot_history(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    rows = db.scalars(select(RaidLoot).where(RaidLoot.user_id == user.id).order_by(RaidLoot.id.desc()).limit(50))
    return {"items": [{"raid_id": r.raid_id, "name": r.item.get("name"), "item": {k: v for k, v in r.item.items() if k != "name"},
                       "rare": r.rare, "chance": r.probability, "roll": r.roll, "at": as_utc(r.created_at).isoformat()}
                      for r in rows]}


# ------------------------------------------------------------------ co-op (up to 5 players, one fight)
def lobby_view(db: Session, lb: RaidLobby, viewer: str) -> dict:
    b = boss_conf(lb.boss_code)
    mem = []
    for m in lb.members:
        c = card(db, m["user_id"], viewer)
        mem.append({"user_id": m["user_id"], "nickname": c["nickname"], "is_ai": c["is_ai"], "power": c["power"]})
    return {"id": lb.id, "boss_code": lb.boss_code, "boss_name": b["name"], "leader_id": lb.leader_id,
            "members": mem, "max": R_()["coop_max_players"], "status": lb.status, "result": lb.result,
            "hp": R_()["coop_hp_per_member"] * max(1, len(lb.members)), "created_at": as_utc(lb.created_at).isoformat()}


def _expire_lobbies(db: Session) -> None:
    lim = utcnow() - timedelta(minutes=R_()["coop_lobby_minutes"])
    for lb in db.scalars(select(RaidLobby).where(RaidLobby.status == "open", RaidLobby.created_at < lim)):
        lb.status = "cancelled"


@router.get("/coop")
def coop_list(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    _expire_lobbies(db)
    rows = db.scalars(select(RaidLobby).where(RaidLobby.status == "open").order_by(RaidLobby.created_at.desc()).limit(30)).all()
    mine = db.scalars(select(RaidLobby).where(RaidLobby.status == "done").order_by(RaidLobby.created_at.desc()).limit(30)).all()
    db.commit()
    st = attempts(db, user.id, "coop")
    return {"open": [lobby_view(db, lb, user.id) for lb in rows],
            "recent": [lobby_view(db, lb, user.id) for lb in mine if any(m["user_id"] == user.id for m in lb.members)][:5],
            "bosses": [{"code": c, "name": boss_conf(c)["name"]} for c in R_()["coop_bosses"]],
            "attempts": int(st.attempts), "max_attempts": max_attempts(db, user.id, "coop")}


class LobbyIn(BaseModel):
    boss_code: str = Field(max_length=32)


@router.post("/coop/create")
def coop_create(body: LobbyIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    if body.boss_code not in R_()["coop_bosses"]:
        raise GameError("not_found", "Этот босс недоступен для совместной охоты", 404)
    if db.scalar(select(RaidLobby).where(RaidLobby.leader_id == user.id, RaidLobby.status == "open")):
        raise GameError("busy", "У вас уже есть открытый сбор", 409)
    freeze_squad(db, user.id)  # validates the squad now
    lb = RaidLobby(boss_code=body.boss_code, leader_id=user.id, members=[{"user_id": user.id}])
    db.add(lb)
    db.commit()
    return lobby_view(db, lb, user.id)


@router.post("/coop/{lobby_id}/join")
def coop_join(lobby_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    lb = db.get(RaidLobby, lobby_id, with_for_update=True)
    if lb is None or lb.status != "open":
        raise GameError("not_found", "Сбор недоступен", 404)
    if any(m["user_id"] == user.id for m in lb.members):
        return lobby_view(db, lb, user.id)
    if len(lb.members) >= R_()["coop_max_players"]:
        raise GameError("full", "Отряд уже собран", 409)
    freeze_squad(db, user.id)
    lb.members = lb.members + [{"user_id": user.id}]
    db.commit()
    return lobby_view(db, lb, user.id)


@router.post("/coop/{lobby_id}/add-ai")
def coop_add_ai(lobby_id: str, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Leader may fill a free slot with an AI ally (PvE only, labelled as AI)."""
    lb = db.get(RaidLobby, lobby_id, with_for_update=True)
    if lb is None or lb.status != "open" or lb.leader_id != user.id:
        raise GameError("not_found", "Сбор недоступен", 404)
    if len(lb.members) >= R_()["coop_max_players"]:
        raise GameError("full", "Отряд уже собран", 409)
    taken = {m["user_id"] for m in lb.members}
    me = db.get(PlayerProfile, user.id)
    cand = db.scalars(select(PlayerProfile).where(PlayerProfile.is_ai.is_(True), PlayerProfile.user_id.notin_(taken))
                      .order_by(func.abs(PlayerProfile.level - me.level)).limit(5)).all()
    if not cand:
        raise GameError("no_ai", "Сейчас нет свободных ИИ-союзников", 409)
    lb.members = lb.members + [{"user_id": cand[0].user_id}]
    db.commit()
    return lobby_view(db, lb, user.id)


@router.post("/coop/{lobby_id}/start")
def coop_start(lobby_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
               db: Session = Depends(get_db)):
    def do():
        lb = db.get(RaidLobby, lobby_id, with_for_update=True)
        if lb is None or lb.status != "open" or lb.leader_id != user.id:
            raise GameError("not_found", "Сбор недоступен", 404)
        humans = [m["user_id"] for m in lb.members if not db.get(PlayerProfile, m["user_id"]).is_ai]
        for uid in humans:  # every human spends one co-op attempt (or a ticket for the leader)
            use_attempt(db, uid, "coop", ticket=(uid == user.id))
        b = boss_conf(lb.boss_code)
        hp_max = R_()["coop_hp_per_member"] * len(lb.members)
        hp = hp_max
        waves, leader_sim = [], None
        base_seed = secrets.randbits(40)
        for i, m in enumerate(lb.members):  # one fight, squads enter in waves; the boss HP is shared
            if hp <= 0:
                break
            sim, dmg, pidx, _ = fight(db, m["user_id"], b, lb.boss_code, hp, hp_max, 1, base_seed + i)
            hp -= dmg
            waves.append({"user_id": m["user_id"], "nickname": card(db, m["user_id"])["nickname"],
                          "is_ai": card(db, m["user_id"])["is_ai"], "damage": dmg, "phase": pidx})
            if m["user_id"] == user.id:
                leader_sim = sim
        victory = hp <= 0
        lb.status = "done"
        lb.result = {"victory": victory, "hp_max": hp_max, "hp_left": max(0, hp), "waves": waves}
        if victory:
            loot = roll_loot(db, lb.id, humans, b, base=R_()["coop_reward"])
        else:
            loot = {uid: [] for uid in humans}
            for uid in humans:
                give(db, uid, {k: v // 3 for k, v in R_()["coop_reward"].items()}, "coop_raid", lb.id)
        for uid, items in loot.items():
            total: dict[str, int] = {}
            for it in items:
                for k, v in it["item"].items():
                    total[k] = total.get(k, 0) + int(v)
            if total:
                give(db, uid, total, "coop_raid", lb.id)
            P.on(db, uid, "raid_attack", next((w["damage"] for w in waves if w["user_id"] == uid), 0), ref=lb.id)
        lb.result = {**lb.result, "loot": {card(db, k)["nickname"]: v for k, v in loot.items()}}
        return {"lobby": lobby_view(db, lb, user.id), "simulation": leader_sim, "wallet": wallet_dict(db, user.id)}
    return run_idempotent(db, user.id, key, f"coop_start:{lobby_id}", {}, do)


_ = (Guild, FACTION_ADV)
