"""Deterministic real-time auto-battle engine (all units act simultaneously).

Server-authoritative: the server simulates with its own seed; the client replays the
time-stamped event log. Same (teams, seed) -> identical log (covered by tests).

Engine v3 (hero kits): every unit has a basic attack, up to two active skills on cooldowns,
an ultimate at 100 energy, a passive and an optional unique mechanic. Abilities are lists of
generic effects defined in data (app/game/content/roster.json):
  damage, heal, shield, buff, debuff, mark, delay, stun, taunt, cleanse, dispel, summon
Unique hero mechanics are small hooks keyed by mechanic id (see MECHANICS below) with all
numbers coming from data. Control is bounded: capped duration, reduced by control resistance,
followed by a short immunity window (no infinite stuns).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import roster as R
from .data import STAR_MULT

TICK = 0.1
MAX_TIME = 90.0
MOVE_SPEED = 2.4
WINDUP = {"melee": 0.32, "ranged": 0.55}
SLOT_POS = {0: (-2.4, -0.9), 1: (-2.4, 0.9), 2: (-4.4, -1.8), 3: (-4.6, 0.0), 4: (-4.4, 1.8)}
FRONT_SLOTS = (0, 1)
SEPARATION = 1.1
Z_LIMIT = 2.6
MAX_ROUNDS = int(MAX_TIME)
RANGED_CLASSES = ("ranger", "mage", "healer", "summoner")
POSITIVE_STATS = {"atk", "def", "spd", "dr", "cc_resist", "regen", "crit", "dodge"}
CONTROL_STATS = {"spd"}  # slows count as "controlled" for predators


def hero_stats(hero: dict, level: int, stars: int = 0, atk_pct: float = 0.0, hp_pct: float = 0.0) -> dict:
    g = (hero.get("extra") or {}).get("growth") or {}
    rm = R.RARITY_MULT[hero["rarity"]] * (1 + STAR_MULT * stars)

    def lv(stat: str) -> float:
        return 1 + float(g.get(stat, 0.06)) * (level - 1)

    return {
        "hp": int(hero["base_hp"] * rm * lv("hp") * (1 + hp_pct)),
        "atk": int(hero["base_atk"] * rm * lv("atk") * (1 + atk_pct)),
        "def": int(hero["base_def"] * rm * lv("def")),
        "spd": hero["base_spd"],
    }


def power_rating(stats: dict) -> int:
    return int(stats["hp"] * 0.25 + stats["atk"] * 2.2 + stats["def"] * 1.5)


@dataclass
class Unit:
    uid: str
    side: int
    slot: int
    code: str
    name: str
    model: str
    faction: str
    cls: str
    rarity: int
    level: int
    hp: int
    max_hp: int
    atk: int
    df: int
    spd: int
    kit: dict
    strong_against: str | None
    crit: float = 0.1
    crit_dmg: float = 1.5
    range: float = 1.8
    x: float = 0.0
    z: float = 0.0
    energy: int = 0
    shield: int = 0
    statuses: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)
    cds: dict = field(default_factory=dict)
    next_attack: float = 0.0
    stunned_until: float = 0.0
    cc_immune_until: float = 0.0
    delay_immune_until: float = 0.0
    taunted_by: str | None = None
    taunt_until: float = 0.0
    moving: bool = False
    last_pos_log: float = -1.0
    skill_level: int = 1  # 1 + stars; scales skills and ultimate (+skill_power_per_level each)
    summon_of: str | None = None
    expires: float = 0.0
    mech: dict = field(default_factory=dict)
    alive: bool = True

    @property
    def ranged(self) -> bool:
        return self.range > 3.0

    @property
    def mechanic_id(self) -> str | None:
        m = self.kit.get("mechanic") if self.kit else None
        return m["id"] if m else None

    def mparams(self) -> dict:
        m = self.kit.get("mechanic") if self.kit else None
        return (m or {}).get("params", {})

    def pparams(self) -> dict:
        p = self.kit.get("passive") if self.kit else None
        return (p or {}).get("params", {})

    @property
    def passive_type(self) -> str | None:
        p = self.kit.get("passive") if self.kit else None
        return p["type"] if p else None

    def public(self) -> dict:
        return {
            "uid": self.uid, "side": self.side, "slot": self.slot, "code": self.code, "name": self.name,
            "model": self.model, "faction": self.faction, "class": self.cls, "rarity": self.rarity,
            "level": self.level, "hp": self.hp, "max_hp": self.max_hp, "atk": self.atk, "def": self.df,
            "spd": self.spd, "skill": (self.kit.get("ultimate") or {}).get("name", ""), "x": round(self.x, 2),
            "z": round(self.z, 2), "range": self.range, "summon_of": self.summon_of,
        }


def make_unit(side: int, slot: int, hero: dict, stats: dict, level: int, strong_against: str | None) -> Unit:
    px, pz = SLOT_POS[slot]
    extra = hero.get("extra") or {}
    cls = hero["class_code"]
    kit = hero.get("kit") or R.legacy_kit(hero.get("skill") or {}, cls, hero["rarity"])
    rng = float(extra.get("range") or R.class_range(cls))
    return Unit(
        uid=f"{'p' if side == 0 else 'e'}{slot}", side=side, slot=slot, code=hero["code"], name=hero["name"],
        model=hero["model"], faction=hero["faction_code"], cls=cls, rarity=hero["rarity"], level=level,
        hp=stats["hp"], max_hp=stats["hp"], atk=stats["atk"], df=stats["def"], spd=stats["spd"], kit=kit,
        strong_against=strong_against, crit=float(extra.get("crit", 0.12)), crit_dmg=float(extra.get("crit_dmg", 1.5)),
        range=rng, x=px if side == 0 else -px, z=pz,
    )


def faction_synergy(units: list[Unit]) -> tuple[str | None, float]:
    """Team bonus for heroes of the same faction (data: faction_rules.synergy)."""
    counts: dict[str, int] = {}
    for u in units:
        counts[u.faction] = counts.get(u.faction, 0) + 1
    if not counts:
        return None, 0.0
    fac, n = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    table = R.faction_rules()["synergy"]
    bonus = 0.0
    for k, v in table.items():
        if n >= int(k):
            bonus = max(bonus, float(v))
    return (fac if bonus > 0 else None), bonus


def _dist(a: Unit, b: Unit) -> float:
    return math.hypot(a.x - b.x, (a.z - b.z) * 0.6)


class Simulation:
    def __init__(self, team: list[Unit], enemies: list[Unit], seed: int):
        self.cfg = R.battle_cfg()
        self.units: list[Unit] = team + enemies
        self.rng = random.Random(seed)
        self.events: list[dict] = []
        self.t = 0.0
        self._sid = 0
        self.synergy = {}
        for side, group in ((0, team), (1, enemies)):
            fac, bonus = faction_synergy(group)
            self.synergy[side] = {"faction": fac, "bonus": bonus}
            if bonus > 0:
                for u in group:
                    u.atk = int(u.atk * (1 + bonus))
                    u.max_hp = int(u.max_hp * (1 + bonus))
                    u.hp = u.max_hp
        for u in self.units:
            u.next_attack = round(0.4 + self.rng.random() * 0.5, 2)
            for i, sk in enumerate(u.kit.get("skills") or []):
                u.cds[sk.get("id", str(i))] = float(sk.get("first", 3 + i * 3))

    # ------------------------------------------------------------------ helpers
    def alive(self, side: int, include_summons: bool = True) -> list[Unit]:
        return [u for u in self.units if u.alive and u.side == side and (include_summons or not u.summon_of)]

    def unit(self, uid: str) -> Unit | None:
        for u in self.units:
            if u.uid == uid:
                return u
        return None

    def stat(self, u: Unit, stat: str) -> float:
        return sum(s["value"] for s in u.statuses if s["stat"] == stat)

    def atk(self, u: Unit) -> float:
        return u.atk * max(0.2, 1 + self.stat(u, "atk"))

    def defense(self, u: Unit) -> float:
        return u.df * max(0.1, 1 + self.stat(u, "def"))

    def interval(self, u: Unit) -> float:
        return round(1.75 * 100.0 / max(u.spd, 1) / max(0.35, 1 + self.stat(u, "spd")), 3)

    def cc_resist(self, u: Unit) -> float:
        v = self.stat(u, "cc_resist") + u.mech.get("perm_cc_resist", 0.0)
        pt, pp = u.passive_type, u.pparams()
        if pt == "cc_resist_low_hp":
            v += pp.get("base", 0) + pp.get("max_bonus", 0) * (1 - u.hp / u.max_hp)
        elif pt == "cc_resist_static":
            v += pp.get("value", 0)
        return max(0.0, min(0.8, v))

    def controlled(self, u: Unit) -> bool:
        return (u.stunned_until > self.t or u.mech.get("delayed_until", 0) > self.t
                or any(s["stat"] in CONTROL_STATS and s["value"] < 0 for s in u.statuses))

    def debuffed(self, u: Unit) -> bool:
        return any(s["kind"] == "debuff" for s in u.statuses) or bool(u.marks)

    def _log_pos(self, u: Unit, force: bool = False, leap: bool = False) -> None:
        if force or self.t - u.last_pos_log >= 0.3:
            ev = {"t": round(self.t, 2), "type": "pos", "actor": u.uid, "x": round(u.x, 2), "z": round(u.z, 2),
                  "moving": u.moving}
            if leap:
                ev["leap"] = True
            self.events.append(ev)
            u.last_pos_log = self.t

    # ------------------------------------------------------------------ targeting
    def _target(self, u: Unit) -> Unit | None:
        foes = self.alive(1 - u.side)
        if not foes:
            return None
        if u.taunted_by and u.taunt_until > self.t:
            t = self.unit(u.taunted_by)
            if t and t.alive:
                return t
        if u.cls == "ranger":
            in_range = [f for f in foes if _dist(u, f) <= u.range]
            if in_range:
                return min(in_range, key=lambda f: (f.hp, f.uid))
        return min(foes, key=lambda f: (round(_dist(u, f), 2), f.uid))

    def _front(self, foes: list[Unit], n: int) -> list[Unit]:
        return sorted(foes, key=lambda f: (abs(f.x), f.uid))[:n]

    def resolve(self, actor: Unit, sel: str, target: Unit | None, prev: list[Unit]) -> list[Unit]:
        foes = self.alive(1 - actor.side)
        allies = self.alive(actor.side)
        name, _, arg = sel.partition(":")
        if name == "same":
            return [p for p in prev if p.alive]
        if name == "target":
            return [target] if target and target.alive else (self._front(foes, 1) if foes else [])
        if name == "self":
            return [actor]
        if name == "all_allies":
            return allies
        if name == "own_summons":
            return [a for a in allies if a.summon_of == actor.uid]
        if name == "all_enemies":
            return foes
        if not foes and name.endswith("enemy") or not foes and name in ("front_row", "random_enemies", "hunt",
                                                                       "lowest_hp_back", "marked", "most_marked",
                                                                       "marked_or_target"):
            return []
        if name == "front_row":
            return self._front(foes, 2)
        if name == "lowest_hp_back":
            back = sorted(foes, key=lambda f: (-abs(f.x), f.uid))[:3]
            return [min(back, key=lambda f: (f.hp / f.max_hp, f.uid))]
        if name == "lowest_hp_ally":
            return [min(allies, key=lambda a: (a.hp / a.max_hp, a.uid))]
        if name == "strongest_ally":
            return [max(allies, key=lambda a: (self.atk(a), a.uid))]
        if name == "highest_atk_enemy":
            return [max(foes, key=lambda f: (self.atk(f), f.uid))]
        if name == "lowest_hp_enemy":
            return [min(foes, key=lambda f: (f.hp, f.uid))]
        if name == "random_enemies":
            n = min(int(arg or 1), len(foes))
            pool = sorted(foes, key=lambda f: f.uid)
            return self.rng.sample(pool, n)
        if name == "marked":
            return [f for f in foes if arg in f.marks]
        if name == "marked_or_target":
            m = [f for f in foes if arg in f.marks]
            return m or ([target] if target and target.alive else self._front(foes, 1))
        if name == "most_marked":
            m = [f for f in foes if arg in f.marks]
            return [max(m, key=lambda f: (f.marks[arg]["stacks"], f.uid))] if m else []
        if name == "hunt":
            n = int(arg or 3)
            prey = sorted([f for f in foes if "prey" in f.marks], key=lambda f: (f.hp, f.uid))
            rest = sorted([f for f in foes if "prey" not in f.marks], key=lambda f: (f.hp, f.uid))
            return (prey + rest)[:n]
        return [target] if target else []

    # ------------------------------------------------------------------ statuses
    def add_status(self, src: Unit, tgt: Unit, stat: str, value: float, dur: float) -> str:
        kind = "buff" if (value > 0) == (stat in POSITIVE_STATS) else "debuff"
        if stat == "accuracy":
            kind = "debuff" if value > 0 else "buff"
        if stat == "heal_received":
            kind = "debuff" if value < 0 else "buff"
        if kind == "debuff" and stat in CONTROL_STATS:
            if self.t < tgt.cc_immune_until:
                return ""
            dur *= 1 - self.cc_resist(tgt)
        if src.passive_type == "summon_pact" and kind == "debuff" and any(
                a.summon_of == src.uid for a in self.alive(src.side)):
            dur *= 1 + src.pparams().get("control_bonus", 0)
        tgt.statuses = [s for s in tgt.statuses if not (s["stat"] == stat and s["src"] == src.uid)]
        entry = {"stat": stat, "value": value, "until": self.t + dur, "src": src.uid, "kind": kind}
        if stat == "regen":
            entry["amount"] = self.atk(src) * value
        tgt.statuses.append(entry)
        return f"{stat}{'+' if kind == 'buff' else '-'}"

    def add_mark(self, src: Unit, tgt: Unit, mark: str, stacks: int, dur: float) -> int:
        m = tgt.marks.get(mark)
        mx = self.cfg.get("max_stacks_default", 5)
        if m:
            m["stacks"] = min(mx, m["stacks"] + stacks)
            m["until"] = self.t + dur
        else:
            m = tgt.marks[mark] = {"stacks": stacks, "until": self.t + dur, "src": src.uid}
        self._hook(src, "on_mark", tgt, mark, m["stacks"])
        return m["stacks"]

    def apply_delay(self, src: Unit, tgt: Unit, dur: float) -> bool:
        if not tgt.alive or self.t < tgt.delay_immune_until or self.t < tgt.cc_immune_until:
            return False
        dur = min(self.cfg.get("delay_max", 1.8), dur) * (1 - self.cc_resist(tgt))
        if src.passive_type == "summon_pact" and any(a.summon_of == src.uid for a in self.alive(src.side)):
            dur *= 1 + src.pparams().get("control_bonus", 0)
        if dur <= 0.05:
            return False
        tgt.next_attack = max(tgt.next_attack, self.t) + dur
        for k in tgt.cds:
            tgt.cds[k] += dur
        tgt.mech["delayed_until"] = self.t + dur
        imm = 1.0
        for u in self.alive(src.side):
            if u.mechanic_id == "reality_shift":
                imm = max(imm, u.mparams().get("delay_immunity", 4))
        tgt.delay_immune_until = self.t + imm
        for u in self.alive(src.side):
            if u.passive_type == "delay_energy":
                u.energy = min(100, u.energy + int(u.pparams().get("value", 12)))
        return True

    def apply_stun(self, src: Unit, tgt: Unit, dur: float) -> bool:
        if not tgt.alive or self.t < tgt.cc_immune_until:
            return False
        dur = min(self.cfg.get("control_max", 2.2), dur) * (1 - self.cc_resist(tgt))
        if dur <= 0.05:
            return False
        tgt.stunned_until = self.t + dur
        tgt.cc_immune_until = self.t + dur + self.cfg.get("control_immunity_after", 1.5)
        return True

    # ------------------------------------------------------------------ damage / heal
    def damage(self, actor: Unit, tgt: Unit, mult: float, extra: dict | None = None) -> dict:
        extra = extra or {}
        acc_down = self.stat(actor, "accuracy")
        dodge = self.stat(tgt, "dodge")
        if self.rng.random() < min(0.6, max(0.0, acc_down + dodge)):
            return {"uid": tgt.uid, "miss": True, "hp": tgt.hp}
        adv = R.faction_rules()["advantage_damage"] if actor.strong_against and actor.strong_against == tgt.faction else 0.0
        crit_chance = actor.crit + self.stat(actor, "crit") + self._hook_sum(actor, "crit_bonus", tgt)
        crit = self.rng.random() < min(0.9, crit_chance)
        bonus = self._hook_sum(actor, "out_bonus", tgt) + extra.get("bonus", 0.0)
        if actor.ranged:
            bonus += sum(self._mark_vuln(tgt))
        a = self.atk(actor)
        variance = 0.9 + self.rng.random() * 0.2
        raw = a * mult * (a / (a + self.defense(tgt) * 0.8)) * (1 + adv) * (1 + bonus) * variance
        raw *= actor.crit_dmg if crit else 1.0
        raw *= 1 - min(0.8, self.stat(tgt, "dr") + tgt.mech.get("monolith_dr", 0.0) * (tgt.mech.get("monolith_until", 0) > self.t))
        dmg = max(1, int(raw))
        result = {"uid": tgt.uid, "dmg": dmg, "crit": crit, "adv": adv > 0}
        dmg = self._redirect(tgt, dmg, result)
        absorbed = min(tgt.shield, dmg)
        tgt.shield -= absorbed
        tgt.hp = max(0, tgt.hp - (dmg - absorbed))
        if absorbed:
            result["absorbed"] = absorbed
        gain = max(self.cfg["energy_on_hit_min"], int(dmg / max(tgt.max_hp, 1) * self.cfg["energy_on_hit_scale"]))
        tgt.energy = min(100, tgt.energy + gain)
        result["hp"] = tgt.hp
        self._hook(tgt, "on_damaged", dmg, actor)
        for ally in self.alive(tgt.side):
            if ally is not tgt:
                self._hook(ally, "on_ally_damaged", tgt, actor)
        if tgt.hp == 0:
            self._kill(tgt, actor, result)
        return result

    def _mark_vuln(self, tgt: Unit) -> list[float]:
        out = []
        for name, m in tgt.marks.items():
            src = self.unit(m["src"])
            if src and src.mechanic_id == "rift_trail" and name == "ash":
                out.append(src.mparams().get("ranged_vuln", 0.12))
        return out

    def _redirect(self, tgt: Unit, dmg: int, result: dict) -> int:
        """Bai-Tash share, root guardian intercept, Arslan guard."""
        if tgt.summon_of:
            return dmg
        for u in self.alive(tgt.side):
            if u is tgt:
                continue
            share = 0.0
            if u.mechanic_id == "immovable_mountain":
                share = u.mparams().get("share", 0.2)
            elif u.summon_of and R.summons().get(u.code, {}).get("intercept"):
                share = R.summons()[u.code]["intercept"]
            elif u.mechanic_id == "pass_oath" and tgt.mech.get("guarded_by") == u.uid:
                share = u.mparams().get("guard_share", 0.5)
                tgt.mech.pop("guarded_by", None)
            if share <= 0:
                continue
            moved = int(dmg * share)
            if moved <= 0:
                continue
            dmg -= moved
            ab = min(u.shield, moved)
            u.shield -= ab
            u.hp = max(0, u.hp - (moved - ab))
            result.setdefault("redirect", []).append({"uid": u.uid, "dmg": moved, "hp": u.hp})
            self._hook(u, "on_damaged", moved, None)
            if u.hp == 0:
                self._kill(u, None, {})
        return dmg

    def _kill(self, tgt: Unit, killer: Unit | None, result: dict) -> None:
        if not tgt.alive:
            return
        tgt.alive = False
        if result is not None:
            result["killed"] = True
        if killer:
            self._hook(killer, "on_kill", tgt)
        # mark transfer (Zarkhan passive)
        for name, m in list(tgt.marks.items()):
            src = self.unit(m["src"])
            if src and src.alive and src.passive_type == "mark_transfer" and name == src.pparams().get("mark"):
                foes = [f for f in self.alive(tgt.side) if f is not tgt]
                if foes:
                    strongest = max(foes, key=lambda f: (self.atk(f), f.uid))
                    strongest.marks[name] = dict(m)
        if tgt.summon_of:
            owner = self.unit(tgt.summon_of)
            if owner and owner.alive and owner.passive_type == "summon_pact":
                ally = min(self.alive(owner.side), key=lambda a: (a.hp / a.max_hp, a.uid), default=None)
                if ally:
                    ally.shield += int(owner.max_hp * owner.pparams().get("shield_hp", 0.18))
            self.events.append({"t": round(self.t, 2), "type": "despawn", "actor": tgt.uid})

    def heal(self, src: Unit, tgt: Unit, amount: float) -> dict:
        amount *= max(0.0, 1 + self.stat(tgt, "heal_received"))
        healed = int(min(amount, tgt.max_hp - tgt.hp))
        tgt.hp += max(0, healed)
        if src.passive_type == "first_heal_resist" and not tgt.mech.get("healed_once"):
            tgt.mech["healed_once"] = True
            tgt.mech["perm_cc_resist"] = tgt.mech.get("perm_cc_resist", 0) + src.pparams().get("value", 0.2)
        self._hook(src, "on_heal_done", tgt)
        self._support_event(src)
        return {"uid": tgt.uid, "heal": max(0, healed), "hp": tgt.hp}

    def _support_event(self, src: Unit) -> None:
        self._hook(src, "on_support", src)
        for ally in self.alive(src.side):
            if ally is not src and ally.passive_type == "bloom_accel":
                self._hook(ally, "on_ally_support", src)

    # ------------------------------------------------------------------ effects
    def run_effects(self, actor: Unit, effects: list[dict], target: Unit | None, power: float = 1.0) -> list[dict]:
        results: list[dict] = []
        prev: list[Unit] = []
        dispelled = 0
        for eff in effects:
            et = eff["type"]
            repeat = int(eff.get("repeat", 1))
            for rep in range(repeat):
                tg = self.resolve(actor, eff.get("target", "target"), target, prev)
                if et != "summon" and not tg:
                    continue
                if eff.get("target") != "same":
                    prev = tg
                if et == "damage":
                    for t in tg:
                        for h in range(int(eff.get("hits", 1))):
                            if not t.alive:
                                break
                            bonus = eff.get("ramp", 0.0) * rep + eff.get("per_dispel", 0.0) * dispelled
                            for mk, bv in (eff.get("bonus_vs_mark") or {}).items():
                                if mk in t.marks:
                                    bonus += bv
                            r = self.damage(actor, t, float(eff.get("mult", 1.0)) * power, {"bonus": bonus})
                            results.append(r)
                            if eff.get("mark") and t.alive:
                                self.add_mark(actor, t, eff["mark"], 1, 8)
                elif et == "heal":
                    for t in tg:
                        results.append(self.heal(actor, t, self.atk(actor) * float(eff.get("mult", 1.0)) * power))
                elif et == "shield":
                    for t in tg:
                        amt = int((actor.max_hp * eff["hp_mult"] if "hp_mult" in eff else self.atk(actor) * eff.get("mult", 1.0)) * power)
                        t.shield += amt
                        results.append({"uid": t.uid, "shield": t.shield, "hp": t.hp})
                    self._support_event(actor)
                elif et in ("buff", "debuff"):
                    for t in tg:
                        tag = self.add_status(actor, t, eff["stat"], float(eff["value"]), float(eff.get("dur", 5)))
                        if tag:
                            results.append({"uid": t.uid, "applied": [tag], "hp": t.hp})
                    if et == "buff":
                        self._support_event(actor)
                elif et == "mark":
                    for t in tg:
                        st = self.add_mark(actor, t, eff["mark"], int(eff.get("stacks", 1)), float(eff.get("dur", 8)))
                        results.append({"uid": t.uid, "applied": [f"mark:{eff['mark']}:{st}"], "hp": t.hp})
                elif et == "delay":
                    for t in tg:
                        if self.apply_delay(actor, t, float(eff.get("dur", 1.0))):
                            results.append({"uid": t.uid, "delayed": True, "hp": t.hp})
                elif et == "stun":
                    for t in tg:
                        if self.apply_stun(actor, t, float(eff.get("dur", 2.0))):
                            results.append({"uid": t.uid, "stunned": True, "hp": t.hp})
                elif et == "taunt":
                    for t in tg:
                        t.taunted_by, t.taunt_until = actor.uid, self.t + float(eff.get("dur", 3))
                        results.append({"uid": t.uid, "applied": ["taunt"], "hp": t.hp})
                elif et == "cleanse":
                    for t in tg:
                        bad = [s for s in t.statuses if s["kind"] == "debuff"][: int(eff.get("count", 1))]
                        for s in bad:
                            t.statuses.remove(s)
                        if bad:
                            results.append({"uid": t.uid, "removed": [s["stat"] for s in bad], "hp": t.hp})
                elif et == "dispel":
                    for t in tg:
                        good = [s for s in t.statuses if s["kind"] == "buff"][: int(eff.get("count", 1))]
                        for s in good:
                            t.statuses.remove(s)
                        if good:
                            dispelled += len(good)
                            results.append({"uid": t.uid, "removed": [s["stat"] for s in good], "hp": t.hp})
                    if dispelled:
                        self._hook(actor, "on_dispel", dispelled)
                elif et == "summon":
                    s = self.summon(actor, eff["summon"], float(eff.get("dur", 10)))
                    if s:
                        results.append({"uid": s.uid, "summoned": True, "hp": s.hp})
        return results

    def summon(self, owner: Unit, code: str, dur: float) -> Unit | None:
        spec = R.summons().get(code)
        if not spec:
            return None
        mine = [a for a in self.alive(owner.side) if a.summon_of == owner.uid]
        if len(mine) >= self.cfg.get("summon_limit_per_owner", 2):
            oldest = min(mine, key=lambda a: a.expires)
            self._kill(oldest, None, {})
        self._sid += 1
        buff = 1 + owner.mparams().get("summon_buff", 0.0)
        hp = int(owner.max_hp * spec["hp"])
        u = Unit(uid=f"{'p' if owner.side == 0 else 'e'}s{self._sid}", side=owner.side, slot=9, code=code,
                 name=spec["name"], model=spec["model"], faction=owner.faction, cls=spec["class"],
                 rarity=owner.rarity, level=owner.level, hp=hp, max_hp=hp, atk=int(owner.atk * spec["atk"] * buff),
                 df=int(owner.df * spec["def"]), spd=spec["spd"],
                 kit={"basic": {"name": "", "effects": [{"type": "damage", "target": "target", "mult": 1.0}]},
                      "skills": [], "ultimate": None, "passive": None, "mechanic": None},
                 strong_against=owner.strong_against, crit=0.05, range=float(spec["range"]),
                 x=owner.x + (0.9 if owner.side == 0 else -0.9), z=max(-Z_LIMIT, min(Z_LIMIT, owner.z + 0.8)),
                 summon_of=owner.uid, expires=self.t + dur)
        u.next_attack = self.t + 0.6
        if spec.get("aura_dr"):
            for a in self.alive(owner.side):
                self.add_status(u, a, "dr", spec["aura_dr"], dur)
        self.units.append(u)
        self.events.append({"t": round(self.t, 2), "type": "summon", "actor": owner.uid, "unit": u.public(),
                            "dur": dur})
        return u

    # ------------------------------------------------------------------ mechanics (data-parametrised hooks)
    def _hook(self, u: Unit, hook: str, *args) -> None:
        if not u or not u.alive:
            return
        mid = u.mechanic_id
        if mid:
            fn = getattr(self, f"_m_{mid}_{hook}", None)
            if fn:
                fn(u, *args)
        pt = u.passive_type
        if pt:
            fn = getattr(self, f"_p_{pt}_{hook}", None)
            if fn:
                fn(u, *args)

    def _hook_sum(self, u: Unit, hook: str, *args) -> float:
        total = 0.0
        for kind, key in (("m", u.mechanic_id), ("p", u.passive_type)):
            if key:
                fn = getattr(self, f"_{kind}_{key}_{hook}", None)
                if fn:
                    total += fn(u, *args)
        return total

    def _mech_event(self, u: Unit, name: str, results: list[dict]) -> None:
        self.events.append({"t": round(self.t, 2), "type": "mechanic", "actor": u.uid, "target": u.uid,
                            "name": name, "impact": round(self.t + 0.25, 2), "energy": u.energy, "targets": results})

    # Arslan-Kara — Клятва перевала
    def _m_pass_oath_on_basic(self, u: Unit, tgt: Unit) -> None:
        p = u.mparams()
        u.mech["stacks"] = u.mech.get("stacks", 0) + 1
        if u.mech["stacks"] >= p["stacks"]:
            u.mech["stacks"] = 0
            res = []
            for a in self.alive(u.side):
                self.add_status(u, a, "atk", p["team_atk"], p["dur"])
                self.add_status(u, a, "dr", p["team_dr"], p["dur"])
                res.append({"uid": a.uid, "applied": ["atk+", "dr+"], "hp": a.hp})
            self._mech_event(u, "Клятва перевала", res)

    def _m_pass_oath_on_ally_damaged(self, u: Unit, ally: Unit, attacker: Unit | None) -> None:
        p = u.mparams()
        if ally.hp / ally.max_hp < p["guard_hp"] and self.t >= u.mech.get("guard_ready", 0) and not ally.summon_of:
            ally.mech["guarded_by"] = u.uid
            u.mech["guard_ready"] = self.t + p["guard_cd"]
            self._mech_event(u, "Заслон Арслана", [{"uid": ally.uid, "applied": ["guard"], "hp": ally.hp}])

    # Bai-Tash — Неподвижная гора
    def _m_immovable_mountain_on_damaged(self, u: Unit, dmg: int, attacker: Unit | None) -> None:
        p = u.mparams()
        u.mech["stone"] = u.mech.get("stone", 0) + dmg
        if u.mech["stone"] >= u.max_hp * p["stone_threshold"]:
            u.mech["stone"] = 0
            res = []
            for a in self.alive(u.side):
                a.shield += int(u.max_hp * p["team_shield_hp"])
                res.append({"uid": a.uid, "shield": a.shield, "hp": a.hp})
            self._mech_event(u, "Каменная энергия", res)
        if u.alive and u.hp / u.max_hp < p["monolith_hp"] and not u.mech.get("monolith_used"):
            u.mech["monolith_used"] = True
            u.mech["monolith_until"] = self.t + p["monolith_dur"]
            u.mech["monolith_dr"] = p["monolith_dr"]
            u.next_attack = self.t + p["monolith_dur"]
            r = self.heal(u, u, u.max_hp * p["monolith_heal"])
            self._mech_event(u, "Монолитный покой", [r])

    # Safariy — Ритм рун / Читающий след
    def _m_rune_rhythm_on_mark(self, u: Unit, tgt: Unit, mark: str, stacks: int) -> None:
        if mark != "wind" or not tgt.alive:
            return
        p = u.mparams()
        res = []
        if stacks == p["slow_at"]:
            self.add_status(u, tgt, "spd", p["slow"], p["dur"])
            res.append({"uid": tgt.uid, "applied": ["spd-"], "hp": tgt.hp})
        if stacks >= p["acc_at"]:
            self.add_status(u, tgt, "accuracy", p["acc"], p["dur"])
            ok = self.apply_delay(u, tgt, p["interrupt"])
            res.append({"uid": tgt.uid, "applied": ["accuracy-"], "delayed": ok, "hp": tgt.hp})
            tgt.marks.pop("wind", None)
        if res:
            self._mech_event(u, "Ритм рун", res)

    def _p_mark_empower_on_mark(self, u: Unit, tgt: Unit, mark: str, stacks: int) -> None:
        p = u.pparams()
        u.mech["empower"] = min(p["max"], u.mech.get("empower", 0.0) + p["per_mark"])

    def _p_mark_empower_out_bonus(self, u: Unit, tgt: Unit) -> float:
        v = u.mech.get("empower", 0.0)
        u.mech["empower"] = 0.0
        return v

    # Ai-Tulgan — Песнь пути
    def _m_path_song_on_heal_done(self, u: Unit, tgt: Unit) -> None:
        p = u.mparams()
        u.mech["notes"] = u.mech.get("notes", 0) + 1
        if u.mech["notes"] >= p["notes"]:
            u.mech["notes"] = 0
            res = []
            for a in self.alive(u.side):
                bad = [s for s in a.statuses if s["kind"] == "debuff"][: p["cleanse"]]
                for s in bad:
                    a.statuses.remove(s)
                self.add_status(u, a, "spd", p["haste"], p["dur"])
                res.append({"uid": a.uid, "applied": ["spd+"], "removed": [s["stat"] for s in bad], "hp": a.hp})
            self._mech_event(u, "Мелодия перевала", res)

    # Yurek — Чтение следа / Знает тропы
    def _m_read_trail_on_basic(self, u: Unit, tgt: Unit) -> None:
        if not tgt.alive:
            return
        p = u.mparams()
        if "trail" not in tgt.marks:
            self.add_mark(u, tgt, "trail", 1, 10)
        else:
            st = self.add_mark(u, tgt, "trail", 1, 10)
            self.add_status(u, tgt, "def", p["def_per_hit"] * min(st, p["max_stacks"]), 6)

    def _m_read_trail_out_bonus(self, u: Unit, tgt: Unit) -> float:
        return u.mparams()["lone_bonus"] if len(self.alive(tgt.side, include_summons=False)) == 1 else 0.0

    def _p_crit_vs_marked_crit_bonus(self, u: Unit, tgt: Unit) -> float:
        p = u.pparams()
        return p["value"] if p["mark"] in tgt.marks else 0.0

    # Sumbel — Круг живых корней (intercept + summon buff are data/engine driven)

    # Ak-Bure — Охота стаи / Чутьё хищника
    def _m_pack_hunt_out_bonus(self, u: Unit, tgt: Unit) -> float:
        p = u.mparams()
        if self.t >= u.mech.get("hunt_ready", 0) and (self.controlled(tgt) or self.debuffed(tgt)):
            u.mech["hunt_ready"] = self.t + p["cd"]
            u.mech["pending_interrupt"] = tgt.uid
            return p["bonus"]
        return 0.0

    def _m_pack_hunt_on_basic(self, u: Unit, tgt: Unit) -> None:
        if u.mech.pop("pending_interrupt", None) == tgt.uid and tgt.alive:
            ok = self.apply_delay(u, tgt, u.mparams()["interrupt"])
            self._mech_event(u, "Охота стаи", [{"uid": tgt.uid, "delayed": ok, "hp": tgt.hp}])

    def _p_predator_out_bonus(self, u: Unit, tgt: Unit) -> float:
        return u.pparams()["vs_controlled"] if self.controlled(tgt) else 0.0

    def _p_predator_on_kill(self, u: Unit, victim: Unit) -> None:
        p = u.pparams()
        self.add_status(u, u, "dodge", p["dodge"], p["dur"])

    # Tan-Chechek — Цикл цветения / После зимы
    def _m_bloom_cycle_on_support(self, u: Unit, src: Unit) -> None:
        self._bloom(u, 1.0)

    def _p_bloom_accel_on_ally_support(self, u: Unit, src: Unit) -> None:
        self._bloom(u, u.pparams()["progress"])

    def _bloom(self, u: Unit, amount: float) -> None:
        if u.mech.get("blooming"):
            return
        p = u.mparams()
        u.mech["bloom"] = u.mech.get("bloom", 0.0) + amount
        if u.mech["bloom"] >= p["stages"]:
            u.mech["bloom"] = 0.0
            u.mech["blooming"] = True
            res = []
            for a in self.alive(u.side):
                r = self.heal(u, a, self.atk(u) * p["wave_heal"])
                self.add_status(u, a, "atk", p["wave_atk"], p["dur"])
                r["applied"] = ["atk+"]
                res.append(r)
            u.mech["blooming"] = False
            self._mech_event(u, "Цветение", res)

    # Vargat — Сломанная клятва / Не служит тирану
    def _m_broken_oath_on_dispel(self, u: Unit, n: int) -> None:
        p = u.mparams()
        u.mech["rage"] = min(p["max"], u.mech.get("rage", 0) + n)

    def _m_broken_oath_out_bonus(self, u: Unit, tgt: Unit) -> float:
        r = u.mech.get("rage", 0)
        u.mech["rage"] = 0
        return r * u.mparams()["per_charge"]

    def _p_dispel_resist_on_dispel(self, u: Unit, n: int) -> None:
        p = u.pparams()
        self.add_status(u, u, "cc_resist", p["value"], p["dur"])

    # Morai — Сдвиг реальности (explosion on mark expiry; delay energy is a passive in apply_delay)
    def _expire_marks(self, u: Unit) -> None:
        for name, m in list(u.marks.items()):
            if m["until"] <= self.t:
                u.marks.pop(name)
                src = self.unit(m["src"])
                if name == "rift" and src and src.alive and src.mechanic_id == "reality_shift" and u.alive:
                    r = self.damage(src, u, src.mparams()["explode"])
                    self._mech_event(src, "Взрыв разлома", [r])

    # Zarkhan — След разлома: heal reduction on marked targets
    def _m_rift_trail_on_basic(self, u: Unit, tgt: Unit) -> None:
        if tgt.alive and "ash" in tgt.marks:
            self.add_status(u, tgt, "heal_received", -u.mparams()["heal_cut"], 6)

    # Ur-Kaan — Дыхание печати / Древнее терпение
    def _m_seal_breath_on_damaged(self, u: Unit, dmg: int, attacker: Unit | None) -> None:
        p = u.mparams()
        u.mech["seal"] = u.mech.get("seal", 0.0) + dmg / max(u.max_hp, 1) * p["seal_scale"]
        if u.mech["seal"] >= 100:
            u.mech["seal"] = 0.0
            s = self.summon(u, "dragon_echo", p["echo_dur"] + 2)
            if s:
                self._mech_event(u, "Драконье эхо", [{"uid": s.uid, "summoned": True, "hp": s.hp}])
        elif u.mech["seal"] >= p["small_at"] and not u.mech.get("small_done"):
            u.mech["small_done"] = True
            s = self.summon(u, "dragon_echo_small", p["echo_dur"])
            if s:
                self._mech_event(u, "Эхо печати", [{"uid": s.uid, "summoned": True, "hp": s.hp}])
        if u.mech.get("seal", 0) < p["small_at"]:
            u.mech["small_done"] = False

    # ------------------------------------------------------------------ actions
    def _cast(self, u: Unit, kind: str, ability: dict, tgt: Unit) -> None:
        if ability.get("leap") and tgt:
            u.x = tgt.x + (-1.2 if u.side == 0 else 1.2)
            u.z = tgt.z
            self._log_pos(u, True, leap=True)
        power = 1.0 if kind == "attack" else 1 + self.cfg.get("skill_power_per_level", 0.05) * (u.skill_level - 1)
        results = self.run_effects(u, ability.get("effects", []), tgt, power)
        if kind == "attack":
            self._hook(u, "on_basic", tgt)
            u.energy = min(100, u.energy + self.cfg["energy_per_basic"])
        elif kind == "skill":
            u.energy = min(100, u.energy + self.cfg.get("energy_per_skill", 0))
        windup = WINDUP["ranged" if u.ranged else "melee"] * (1.0 if kind == "attack" else 1.4)
        self.events.append({"t": round(self.t, 2), "type": kind, "actor": u.uid, "target": tgt.uid if tgt else "",
                            "name": ability.get("name", "") if kind != "attack" else "",
                            "anim": ability.get("anim", "ultimate" if kind == "ultimate" else "attack"),
                            "impact": round(self.t + windup, 2), "energy": u.energy, "targets": results})

    def _step_unit(self, u: Unit) -> None:
        if not u.alive:
            return
        if u.summon_of and self.t >= u.expires:
            self._kill(u, None, {})
            return
        self._expire_marks(u)
        u.statuses = [s for s in u.statuses if s["until"] > self.t]
        for s in u.statuses:
            if s["stat"] == "regen" and int(self.t * 10) % 10 == 0:
                u.hp = min(u.max_hp, u.hp + int(s.get("amount", 0)))
        if self.t < u.stunned_until or (u.mech.get("monolith_until", 0) > self.t and not u.summon_of):
            return
        tgt = self._target(u)
        if tgt is None:
            return
        d = _dist(u, tgt)
        if d > u.range:
            step = MOVE_SPEED * TICK
            dx, dz = tgt.x - u.x, (tgt.z - u.z) * 0.6
            n = math.hypot(dx, dz) or 1.0
            move = min(step, d - u.range + 0.05)
            u.x += dx / n * move
            u.z += (dz / n * move) / 0.6 * 0.5
            if not u.moving:
                u.moving = True
                self._log_pos(u, True)
            else:
                self._log_pos(u)
            return
        if u.moving:
            u.moving = False
            self._log_pos(u, True)
        if self.t + 1e-9 < u.next_attack:
            return
        ult = u.kit.get("ultimate")
        if ult and u.energy >= 100:
            u.energy = 0
            self._cast(u, "ultimate", ult, tgt)
            u.next_attack = round(self.t + self.interval(u) * 1.3, 3)
            return
        for i, sk in enumerate(u.kit.get("skills") or []):
            key = sk.get("id", str(i))
            if self.t + 1e-9 >= u.cds.get(key, 0):
                u.cds[key] = self.t + float(sk.get("cooldown", 10))
                self._cast(u, "skill", sk, tgt)
                u.next_attack = round(self.t + self.interval(u) * 1.15, 3)
                return
        self._cast(u, "attack", u.kit.get("basic") or {"effects": [{"type": "damage", "target": "target", "mult": 1.0}]}, tgt)
        u.next_attack = round(self.t + self.interval(u), 3)

    def _separate(self) -> None:
        for side in (0, 1):
            team = sorted(self.alive(side), key=lambda u: u.uid)
            for i, a in enumerate(team):
                for b in team[i + 1:]:
                    dx, dz = b.x - a.x, b.z - a.z
                    if abs(dx) < 1.0 and abs(dz) < SEPARATION:
                        push = (SEPARATION - abs(dz)) / 2 + 0.01
                        sgn = 1.0 if (dz > 0 or (dz == 0 and b.slot % 2 == 1)) else -1.0
                        a.z = max(-Z_LIMIT, min(Z_LIMIT, a.z - sgn * push))
                        b.z = max(-Z_LIMIT, min(Z_LIMIT, b.z + sgn * push))
                        for u in (a, b):
                            self._log_pos(u, True)

    def run(self) -> dict:
        winner = None
        while self.t < MAX_TIME and winner is None:
            self._separate()
            for u in sorted(list(self.units), key=lambda x: (-x.spd, x.side, x.uid)):
                self._step_unit(u)
                if not self.alive(1, include_summons=False):
                    winner = 0
                    break
                if not self.alive(0, include_summons=False):
                    winner = 1
                    break
            self.t = round(self.t + TICK, 2)
        return {
            "result": "victory" if winner == 0 else "defeat",
            "duration": round(self.t, 2),
            "rounds": int(math.ceil(self.t)),
            "timeout": winner is None,
            "events": self.events,
            "survivors": [u.uid for u in self.units if u.alive and not u.summon_of],
            "synergy": self.synergy,
        }


def simulate(team: list[Unit], enemies: list[Unit], seed: int) -> dict:
    initial = [u.public() for u in team + enemies]
    sim = Simulation(team, enemies, seed)
    # units after synergy (hp/atk) so the client shows the real values
    initial = [u.public() for u in sim.units]
    out = sim.run()
    out["units"] = initial
    out["seed"] = seed
    out["realtime"] = True
    out["engine"] = 3
    return out
