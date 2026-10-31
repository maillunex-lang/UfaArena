"""Deterministic auto-battle simulation.

Server-authoritative: the server simulates with its own seed and stores the result.
The client receives the event log and only visualises it, so it cannot forge a
victory. Same (teams, seed) -> identical log (covered by tests).

Provisional rules (GDD: формация C / управление D / длительность D / поражение D
не расшифрованы): 5 slots — 0,1 front row, 2,3,4 back row; max 15 rounds,
timeout = defeat; on defeat the player keeps the team and may retry immediately.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .data import RARITY_MULT, STAR_MULT

MAX_ROUNDS = 15
ENERGY_PER_ACTION = 34
ENERGY_ON_HIT = 8
CRIT_CHANCE = 0.12
CRIT_MULT = 1.5
FACTION_ADV = 1.3
FRONT_SLOTS = (0, 1)


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
    energy: int = 0
    shield: int = 0
    stunned: int = 0
    alive: bool = field(default=True)

    def public(self) -> dict:
        return {
            "uid": self.uid, "side": self.side, "slot": self.slot, "code": self.code, "name": self.name,
            "model": self.model, "faction": self.faction, "class": self.cls, "rarity": self.rarity,
            "level": self.level, "hp": self.hp, "max_hp": self.max_hp, "atk": self.atk, "def": self.df,
            "spd": self.spd, "skill": self.skill.get("name", ""),
        }


def make_unit(side: int, slot: int, hero: dict, stats: dict, level: int, strong_against: str | None) -> Unit:
    return Unit(
        uid=f"{'p' if side == 0 else 'e'}{slot}", side=side, slot=slot, code=hero["code"], name=hero["name"],
        model=hero["model"], faction=hero["faction_code"], cls=hero["class_code"], rarity=hero["rarity"],
        level=level, hp=stats["hp"], max_hp=stats["hp"], atk=stats["atk"], df=stats["def"], spd=stats["spd"],
        skill=hero.get("skill") or {}, strong_against=strong_against,
    )


class Simulation:
    def __init__(self, team: list[Unit], enemies: list[Unit], seed: int):
        self.units = team + enemies
        self.rng = random.Random(seed)
        self.events: list[dict] = []

    # ---- helpers
    def alive(self, side: int) -> list[Unit]:
        return [u for u in self.units if u.alive and u.side == side]

    def _pick_enemy(self, actor: Unit, mode: str) -> Unit | None:
        foes = self.alive(1 - actor.side)
        if not foes:
            return None
        if mode == "weakest":
            return min(foes, key=lambda u: (u.hp, u.slot))
        if mode == "random":
            return foes[self.rng.randrange(len(foes))]
        front = [u for u in foes if u.slot in FRONT_SLOTS]
        pool = front or foes
        return min(pool, key=lambda u: u.slot)

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
    def _basic(self, actor: Unit) -> list[dict]:
        mode = "random" if actor.cls in ("ranger", "mage") else "front"
        tgt = self._pick_enemy(actor, mode)
        return [self._damage(actor, tgt, 1.0)] if tgt else []

    def _skill(self, actor: Unit) -> list[dict]:
        kind, power = actor.skill.get("kind", "strike"), float(actor.skill.get("power", 1.5))
        if kind == "aoe":
            return [self._damage(actor, t, power) for t in list(self.alive(1 - actor.side))]
        if kind == "strike":
            mode = "weakest" if actor.cls == "ranger" else "front"
            tgt = self._pick_enemy(actor, mode)
            return [self._damage(actor, tgt, power)] if tgt else []
        if kind == "stun":
            tgt = self._pick_enemy(actor, "front")
            if not tgt:
                return []
            r = self._damage(actor, tgt, power)
            if tgt.alive:
                tgt.stunned = 1
                r["stunned"] = True
            return [r]
        allies = self.alive(actor.side)
        tgt = min(allies, key=lambda u: (u.hp / u.max_hp, u.slot))
        if kind == "heal":
            amount = int(actor.atk * power * 1.6)
            healed = min(amount, tgt.max_hp - tgt.hp)
            tgt.hp += healed
            out = {"uid": tgt.uid, "heal": healed, "hp": tgt.hp}
            if actor.rarity >= 6:
                tgt.shield += int(amount * 0.4)
                out["shield"] = tgt.shield
            return [out]
        # shield
        tgt.shield += int(actor.atk * power * 2.2)
        return [{"uid": tgt.uid, "shield": tgt.shield, "hp": tgt.hp}]

    def run(self) -> dict:
        rnd = 0
        winner = None
        while rnd < MAX_ROUNDS and winner is None:
            rnd += 1
            order = sorted(
                (u for u in self.units if u.alive),
                key=lambda u: (-u.spd, u.side, u.slot),
            )
            for actor in order:
                if not actor.alive:
                    continue
                if actor.stunned:
                    actor.stunned = 0
                    self.events.append({"round": rnd, "actor": actor.uid, "type": "stunned", "targets": []})
                    continue
                if actor.energy >= 100:
                    actor.energy = 0
                    targets = self._skill(actor)
                    ev_type, name = "skill", actor.skill.get("name", "")
                else:
                    actor.energy = min(100, actor.energy + ENERGY_PER_ACTION)
                    targets = self._basic(actor)
                    ev_type, name = "attack", ""
                self.events.append({"round": rnd, "actor": actor.uid, "type": ev_type, "name": name,
                                    "energy": actor.energy, "targets": targets})
                if not self.alive(1):
                    winner = 0
                    break
                if not self.alive(0):
                    winner = 1
                    break
        result = "victory" if winner == 0 else "defeat"
        return {
            "result": result,
            "rounds": rnd,
            "timeout": winner is None,
            "events": self.events,
            "survivors": [u.uid for u in self.units if u.alive],
        }


def simulate(team: list[Unit], enemies: list[Unit], seed: int) -> dict:
    initial = [u.public() for u in team + enemies]
    out = Simulation(team, enemies, seed).run()
    out["units"] = initial
    out["seed"] = seed
    return out
