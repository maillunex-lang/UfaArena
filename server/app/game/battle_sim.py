"""Deterministic real-time auto-battle simulation (all units act simultaneously).

Server-authoritative: the server simulates with its own seed and stores the result; the
client replays the time-stamped event log. Same (teams, seed) -> identical log.

Model: fixed 0.1 s ticks, 90 s limit (timeout = defeat). Side view battlefield: the player's
team on the left (x < 0), enemies on the right. Every unit has its own attack timer derived
from speed; melee units walk up to their target, ranged units shoot from distance; 100 energy
triggers the hero's skill. Provisional rules — see docs/GDD_OPEN_QUESTIONS.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .data import RARITY_MULT, STAR_MULT

TICK = 0.1
MAX_TIME = 90.0
MOVE_SPEED = 2.4
ENERGY_PER_ATTACK = 20
ENERGY_ON_HIT = 6
CRIT_CHANCE = 0.12
CRIT_MULT = 1.5
FACTION_ADV = 1.3
STUN_TIME = 2.2
RANGE = {"guardian": 1.8, "warrior": 1.8, "ranger": 6.5, "mage": 6.0, "healer": 5.5}
WINDUP = {"melee": 0.32, "ranged": 0.55}
# formation slots: 0,1 front row; 2,3,4 back row. (x for the left side, z = depth lane)
SLOT_POS = {0: (-2.4, -0.9), 1: (-2.4, 0.9), 2: (-4.4, -1.8), 3: (-4.6, 0.0), 4: (-4.4, 1.8)}
FRONT_SLOTS = (0, 1)
SEPARATION = 1.1  # min depth gap between teammates standing at the same x
Z_LIMIT = 2.6
MAX_ROUNDS = int(MAX_TIME)  # kept for API compatibility (reported as seconds)


def hero_stats(hero: dict, level: int, stars: int = 0, atk_pct: float = 0.0, hp_pct: float = 0.0) -> dict:
    m = RARITY_MULT[hero["rarity"]] * (1 + 0.06 * (level - 1)) * (1 + STAR_MULT * stars)
    return {
        "hp": int(hero["base_hp"] * m * (1 + hp_pct)),
        "atk": int(hero["base_atk"] * m * (1 + atk_pct)),
        "def": int(hero["base_def"] * m),
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
    skill: dict
    strong_against: str | None
    x: float = 0.0
    z: float = 0.0
    energy: int = 0
    shield: int = 0
    stunned_until: float = 0.0
    next_attack: float = 0.0
    moving: bool = False
    last_pos_log: float = -1.0
    alive: bool = field(default=True)

    @property
    def ranged(self) -> bool:
        return self.cls in ("ranger", "mage", "healer")

    @property
    def interval(self) -> float:
        return round(1.75 * 100.0 / max(self.spd, 1), 3)

    def public(self) -> dict:
        return {
            "uid": self.uid, "side": self.side, "slot": self.slot, "code": self.code, "name": self.name,
            "model": self.model, "faction": self.faction, "class": self.cls, "rarity": self.rarity,
            "level": self.level, "hp": self.hp, "max_hp": self.max_hp, "atk": self.atk, "def": self.df,
            "spd": self.spd, "skill": self.skill.get("name", ""), "x": round(self.x, 2), "z": round(self.z, 2),
            "range": RANGE[self.cls],
        }


def make_unit(side: int, slot: int, hero: dict, stats: dict, level: int, strong_against: str | None) -> Unit:
    px, pz = SLOT_POS[slot]
    return Unit(
        uid=f"{'p' if side == 0 else 'e'}{slot}", side=side, slot=slot, code=hero["code"], name=hero["name"],
        model=hero["model"], faction=hero["faction_code"], cls=hero["class_code"], rarity=hero["rarity"],
        level=level, hp=stats["hp"], max_hp=stats["hp"], atk=stats["atk"], df=stats["def"], spd=stats["spd"],
        skill=hero.get("skill") or {}, strong_against=strong_against,
        x=px if side == 0 else -px, z=pz,
    )


def _dist(a: Unit, b: Unit) -> float:
    return math.hypot(a.x - b.x, (a.z - b.z) * 0.6)


class Simulation:
    def __init__(self, team: list[Unit], enemies: list[Unit], seed: int):
        self.units = team + enemies
        self.rng = random.Random(seed)
        self.events: list[dict] = []
        self.t = 0.0
        for u in self.units:  # stagger the first swings a little so it does not look robotic
            u.next_attack = round(0.4 + self.rng.random() * 0.5, 2)

    def alive(self, side: int) -> list[Unit]:
        return [u for u in self.units if u.alive and u.side == side]

    # ---- targeting
    def _target(self, u: Unit) -> Unit | None:
        foes = self.alive(1 - u.side)
        if not foes:
            return None
        if u.cls == "ranger":
            in_range = [f for f in foes if _dist(u, f) <= RANGE[u.cls]]
            if in_range:
                return min(in_range, key=lambda f: (f.hp, f.slot))
        return min(foes, key=lambda f: (round(_dist(u, f), 2), f.slot))

    def _damage(self, actor: Unit, target: Unit, mult: float) -> dict:
        adv = FACTION_ADV if actor.strong_against and actor.strong_against == target.faction else 1.0
        variance = 0.9 + self.rng.random() * 0.2
        crit = self.rng.random() < CRIT_CHANCE
        raw = actor.atk * mult * (actor.atk / (actor.atk + target.df * 0.8)) * adv * variance * (CRIT_MULT if crit else 1.0)
        dmg = max(1, int(raw))
        absorbed = min(target.shield, dmg)
        target.shield -= absorbed
        target.hp = max(0, target.hp - (dmg - absorbed))
        target.energy = min(100, target.energy + ENERGY_ON_HIT)
        killed = target.hp == 0
        if killed:
            target.alive = False
        return {"uid": target.uid, "dmg": dmg, "absorbed": absorbed, "crit": crit, "adv": adv > 1,
                "hp": target.hp, "killed": killed}

    # ---- actions
    def _skill(self, actor: Unit, tgt: Unit) -> list[dict]:
        kind, power = actor.skill.get("kind", "strike"), float(actor.skill.get("power", 1.5))
        if kind == "aoe":
            return [self._damage(actor, f, power) for f in list(self.alive(1 - actor.side))]
        if kind == "strike":
            if actor.cls == "ranger":
                tgt = min(self.alive(1 - actor.side), key=lambda f: (f.hp, f.slot))
            return [self._damage(actor, tgt, power)]
        if kind == "stun":
            r = self._damage(actor, tgt, power)
            if tgt.alive:
                tgt.stunned_until = self.t + STUN_TIME
                r["stunned"] = True
            return [r]
        allies = self.alive(actor.side)
        ally = min(allies, key=lambda a: (a.hp / a.max_hp, a.slot))
        if kind == "heal":
            amount = int(actor.atk * power * 1.6)
            healed = min(amount, ally.max_hp - ally.hp)
            ally.hp += healed
            out = {"uid": ally.uid, "heal": healed, "hp": ally.hp}
            if actor.rarity >= 6:
                ally.shield += int(amount * 0.4)
                out["shield"] = ally.shield
            return [out]
        ally.shield += int(actor.atk * power * 2.2)
        return [{"uid": ally.uid, "shield": ally.shield, "hp": ally.hp}]

    def _log_pos(self, u: Unit, force: bool = False) -> None:
        if force or self.t - u.last_pos_log >= 0.3:
            self.events.append({"t": round(self.t, 2), "type": "pos", "actor": u.uid,
                                "x": round(u.x, 2), "z": round(u.z, 2), "moving": u.moving})
            u.last_pos_log = self.t

    def _step_unit(self, u: Unit) -> None:
        if not u.alive or self.t < u.stunned_until:
            return
        tgt = self._target(u)
        if tgt is None:
            return
        rng = RANGE[u.cls]
        d = _dist(u, tgt)
        if d > rng:
            step = MOVE_SPEED * TICK
            dx, dz = tgt.x - u.x, (tgt.z - u.z) * 0.6
            n = math.hypot(dx, dz) or 1.0
            move = min(step, d - rng + 0.05)
            u.x += dx / n * move
            u.z += (dz / n * move) / 0.6 * 0.5  # drift between lanes slowly
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
        is_skill = u.energy >= 100
        if is_skill:
            u.energy = 0
            results = self._skill(u, tgt)
            u.next_attack = round(self.t + u.interval * 1.4, 3)
        else:
            mult = 1.0
            results = [self._damage(u, tgt, mult)]
            u.energy = min(100, u.energy + ENERGY_PER_ATTACK)
            u.next_attack = round(self.t + u.interval, 3)
        impact = round(self.t + WINDUP["ranged" if u.ranged else "melee"] * (1.4 if is_skill else 1.0), 2)
        self.events.append({"t": round(self.t, 2), "type": "skill" if is_skill else "attack", "actor": u.uid,
                            "target": tgt.uid, "name": u.skill.get("name", "") if is_skill else "",
                            "kind": u.skill.get("kind", "") if is_skill else "", "impact": impact,
                            "energy": u.energy, "targets": results})

    def _separate(self) -> None:
        """Keep allies from stacking on one spot: push overlapping teammates apart along depth (z)."""
        for side in (0, 1):
            team = sorted(self.alive(side), key=lambda u: u.slot)
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
            # deterministic order each tick: faster units first, then side, then slot
            for u in sorted(self.units, key=lambda x: (-x.spd, x.side, x.slot)):
                self._step_unit(u)
                if not self.alive(1):
                    winner = 0
                    break
                if not self.alive(0):
                    winner = 1
                    break
            self.t = round(self.t + TICK, 2)
        result = "victory" if winner == 0 else "defeat"
        return {
            "result": result,
            "duration": round(self.t, 2),
            "rounds": int(math.ceil(self.t)),
            "timeout": winner is None,
            "events": self.events,
            "survivors": [u.uid for u in self.units if u.alive],
        }


def simulate(team: list[Unit], enemies: list[Unit], seed: int) -> dict:
    initial = [u.public() for u in team + enemies]
    out = Simulation(team, enemies, seed).run()
    out["units"] = initial
    out["seed"] = seed
    out["realtime"] = True
    return out
