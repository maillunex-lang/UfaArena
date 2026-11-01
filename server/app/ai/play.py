"""AI residents play by the game rules (stages 5 and 12, decision D-02).

A play session calls the very same player API functions as the mobile client (claim the watch chest and quests,
campaign battle + completion, hero level-ups, summoning, caravan module upgrades, formation, guild donation).
Nothing is simulated: resources come only from the same sources as for players and are spent at the same prices.
Every call that changes resources carries an idempotency key derived from the Director task, so a retried task replays
the stored result instead of paying or rewarding twice.

AI-specific limits (admin settings): battles, summons and upgrades per day, a gold reserve by economic strategy and a
hoarding ceiling; VIP experience is never granted to AI (decision P3-01)."""
from __future__ import annotations

import random
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import GameError
from ..core.security import CurrentUser
from ..game import data as D
from ..models import (
    AiPersona, Battle, CampaignNode, Hero, PlayerHero, PlayerProfile, SummonPool,
)
from .sections import Section

SECTION = Section(
    "ai_play",
    {"progression": "rules", "battles_per_day": 8, "summons_per_day": 3, "levelups_per_session": 6,
     "upgrades_per_day": 2, "claim_quests": True, "summon": True, "upgrade_modules": True, "guild_donate": True,
     "reserve_saver": 50, "reserve_balanced": 30, "reserve_spender": 10, "max_hoard_gold": 2000000,
     "rebuild_after_losses": 2, "plays_per_tick": 2},
    {"progression": ("choice", ["rules", "simulated"]), "battles_per_day": ("int", 0, 100),
     "summons_per_day": ("int", 0, 50), "levelups_per_session": ("int", 0, 50), "upgrades_per_day": ("int", 0, 20),
     "claim_quests": ("bool",), "summon": ("bool",), "upgrade_modules": ("bool",), "guild_donate": ("bool",),
     "reserve_saver": ("int", 0, 95), "reserve_balanced": ("int", 0, 95), "reserve_spender": ("int", 0, 95),
     "max_hoard_gold": ("int", 1000, 1000000000), "rebuild_after_losses": ("int", 1, 10),
     "plays_per_tick": ("int", 1, 20)},
    {"progression": "Как растут ИИ: по правилам игры (rules) или упрощённо (simulated, как раньше)",
     "battles_per_day": "Боёв кампании в день на ИИ, максимум", "summons_per_day": "Призывов в день, максимум",
     "levelups_per_session": "Улучшений героев за заход, максимум", "upgrades_per_day": "Улучшений модулей каравана в день",
     "claim_quests": "Забирать награды заданий", "summon": "Призывать героев за эссенцию",
     "upgrade_modules": "Улучшать модули каравана", "guild_donate": "Вносить золото в казну гильдии (по правилам)",
     "reserve_saver": "Запас золота у бережливых, %", "reserve_balanced": "Запас золота у сбалансированных, %",
     "reserve_spender": "Запас золота у транжир, %", "max_hoard_gold": "Потолок накоплений: сверх него ИИ тратит",
     "rebuild_after_losses": "Перестраивать отряд после стольких поражений подряд",
     "plays_per_tick": "Игровых заходов за такт Director, максимум (бережёт процессор сервера)"})
ECONOMY = {"saver": "Бережливый", "balanced": "Сбалансированный", "spender": "Транжира"}


def economy_of(persona: AiPersona) -> str:
    c = persona.counters or {}
    if c.get("economy") in ECONOMY:
        return c["economy"]
    t = persona.traits or {}
    if t.get("patience", 0.5) > 0.62 and t.get("ambition", 0.5) < 0.6:
        return "saver"
    if t.get("ambition", 0.5) > 0.65 or t.get("patience", 0.5) < 0.35:
        return "spender"
    return "balanced"


def _user(persona: AiPersona) -> CurrentUser:
    return CurrentUser(persona.user_id, "ai-director")


def _count(persona: AiPersona, key: str, day: str, delta: int = 0) -> int:
    c = dict(persona.counters or {})
    daily = dict(c.get("daily") or {})
    if daily.get("day") != day:
        daily = {"day": day}
    daily[key] = int(daily.get(key, 0)) + delta
    c["daily"] = daily
    persona.counters = c
    return daily[key]


def wallet(db: Session, user_id: str) -> dict:
    from ..services import wallet_dict
    return wallet_dict(db, user_id)


def _affordable(w: dict, cost: dict, reserve_gold: int = 0) -> bool:
    return all(w.get(k, 0) - (reserve_gold if k == "gold" else 0) >= v for k, v in cost.items())


# ------------------------------------------------------------------ team building (strategy)
def best_formation(db: Session, persona: AiPersona, rng: random.Random, variant: int = 0) -> list[str | None]:
    """Synergy-aware squad: tanks in front by strategy, strongest damage behind, a healer if there is one; a second
    "variant" shuffles the choice after losses (changing strategy)."""
    from ..game.battle_sim import hero_stats, power_rating
    from ..services import hero_dict
    strategy = (persona.counters or {}).get("strategy", "balanced")
    rows = []
    for ph in db.scalars(select(PlayerHero).where(PlayerHero.user_id == persona.user_id)):
        hd = hero_dict(ph.hero)
        rows.append((ph, hd, power_rating(hero_stats(hd, ph.level, ph.stars))))
    if not rows:
        return [None] * 5
    rows.sort(key=lambda r: -r[2])
    if variant:
        head, tail = rows[:3], rows[3:]
        rng.shuffle(tail)
        rows = head + tail
    tanks = [r for r in rows if r[1]["class_code"] in ("guardian", "warrior")]
    healers = [r for r in rows if r[1]["class_code"] in ("healer", "support")]
    n_tanks = {"defensive": 2, "aggressive": 1}.get(strategy, 2 if variant % 2 == 0 else 1)
    pick = tanks[:n_tanks]
    if healers and strategy != "aggressive":
        pick += [h for h in healers[:1] if h not in pick]
    # faction synergy: prefer the most common faction among the strongest heroes
    fac = Counter(r[1]["faction_code"] for r in rows[:8]).most_common(1)
    main_fac = fac[0][0] if fac else None
    rest = sorted([r for r in rows if r not in pick], key=lambda r: (-(r[1]["faction_code"] == main_fac) * 0.15 * r[2] - r[2]))
    pick = (pick + rest)[:5]
    front = [r for r in pick if r[1]["class_code"] in ("guardian", "warrior")][:2]
    back = [r for r in pick if r not in front]
    ordered = front + back
    return ([r[0].id for r in ordered] + [None] * 5)[:5]


def set_team(db: Session, persona: AiPersona, slots: list[str | None]) -> None:
    from ..modules.game import FormationIn, set_formation
    if any(slots):
        set_formation(FormationIn(slots=slots), _user(persona), db)
    from ..social.common import freeze_squad, squad_power
    from ..models import ArenaProfile
    ap = db.get(ArenaProfile, persona.user_id)
    if ap is not None:  # the arena defense follows the main squad (team rebuilt -> defense rebuilt)
        sq = freeze_squad(db, persona.user_id)
        ap.defense, ap.defense_power = sq, squad_power(sq)
        db.commit()


# ------------------------------------------------------------------ one play session
def session(db: Session, persona: AiPersona, task_key: str, rng: random.Random | None = None) -> dict:
    """A short play session by the game rules. Each step commits on its own (like separate client requests)."""
    from ..modules import economy as ECO
    from ..modules import game as GAME
    from ..social.common import day
    rng = rng or random.Random()
    s = SECTION.get(db)
    u = _user(persona)
    today = day()
    log: dict = {"steps": []}

    def key(name: str) -> str:
        """Stable per task and per meaning (node, hero + level, quest…): a retried task replays the same calls."""
        return f"ai{task_key}:{name}"[:64]

    def safe(name: str, fn):
        try:
            r = fn()
            log["steps"].append(name)
            return r
        except GameError as e:
            code = (e.detail or {}).get("code") if isinstance(e.detail, dict) else str(e.detail)
            log.setdefault("skipped", []).append(f"{name}: {code}")
            db.rollback()
            return None

    # 1) the watch chest (AFK) — the main income, same rates as players
    safe("afk", lambda: ECO.afk_claim(u, key("afk"), db))
    # 2) quest rewards
    if s["claim_quests"]:
        for q in [q for q in ECO._quest_list(db, persona.user_id) if q["claimable"]][:5]:
            safe("quest", lambda q=q: ECO.quest_claim(q["code"], u, key("q" + q["code"]), db))
    # 3) campaign battles by the rules (validate -> complete)
    losses_row = int((persona.counters or {}).get("camp_losses_row", 0))
    if losses_row >= s["rebuild_after_losses"] or not any(GAME._formation(db, persona.user_id).slots or []):
        safe("rebuild", lambda: set_team(db, persona, best_formation(db, persona, rng, variant=losses_row)))
    fights = 0
    while fights < 2 and _count(persona, "battles", today) < s["battles_per_day"]:
        from ..services import next_node
        node = next_node(db, persona.user_id)
        if node is None:
            break
        r = safe("battle", lambda node=node: GAME.battle_validate(GAME.BattleIn(node_id=node.code), u, db))
        if r is None:
            break
        _count(persona, "battles", today, 1)
        fights += 1
        res = safe("complete", lambda node=node, r=r: GAME.campaign_complete(node.code, GAME.CompleteIn(battle_id=r["battle_id"]),
                                                                              u, key("c" + node.code), db))
        won = bool(res) and res.get("result") == "victory"
        _after_battle(db, persona, node, won, rng)
        db.commit()
        if not won:
            break  # lost: improve the team before trying again
    # 4) spend by the economic strategy
    econ = economy_of(persona)
    w = wallet(db, persona.user_id)
    reserve = int(w.get("gold", 0) * s[f"reserve_{econ}"] / 100)
    if w.get("gold", 0) > s["max_hoard_gold"]:
        reserve = int(s["max_hoard_gold"] * 0.5)  # anti-hoarding: above the ceiling the AI spends
    slots = [x for x in (GAME._formation(db, persona.user_id).slots or []) if x]
    ups = 0
    for _ in range(s["levelups_per_session"]):
        heroes = [db.get(PlayerHero, x) for x in slots]
        heroes = [h for h in heroes if h is not None and h.level < D.LEVEL_CAP_MVP]
        if not heroes:
            break
        h = min(heroes, key=lambda x: x.level)  # raise the weakest member of the squad
        if not _affordable(wallet(db, persona.user_id), D.level_up_cost(h.level), reserve):
            break
        if safe("levelup", lambda h=h: GAME.level_up(h.id, u, key(f"l{h.id[:12]}:{h.level}"), db)) is None:
            break
        ups += 1
    log["levelups"] = ups
    if s["summon"] and _count(persona, "summons", today) < s["summons_per_day"]:
        pool = db.get(SummonPool, "standard") or db.scalar(select(SummonPool).where(SummonPool.active.is_(True)))
        if pool is not None and _affordable(wallet(db, persona.user_id), pool.cost, reserve):
            n_sum = _count(persona, "summons", today)
            r = safe("summon", lambda: ECO.summon(ECO.SummonIn(pool=pool.code, count=1), u, key(f"s{today}:{n_sum}"), db))
            if r:
                _count(persona, "summons", today, 1)
                _after_summon(db, persona, r)
    if s["upgrade_modules"] and _count(persona, "upgrades", today) < s["upgrades_per_day"]:
        from ..services import building_levels
        lv = building_levels(db, persona.user_id)
        prefer = {"saver": ["storage", "guild_house", "research"], "spender": ["summon_hall", "forge", "training"]}.get(
            econ, ["training", "storage", "forge"])
        for code in prefer + [c for c in D.BUILDINGS if c not in prefer]:
            cfg = D.BUILDINGS[code]
            level = lv.get(code, 1)
            if cfg.get("locked") or level >= cfg["max_level"]:
                continue
            if _affordable(wallet(db, persona.user_id), D.building_upgrade_cost(code, level), reserve):
                if safe("module", lambda code=code, level=level: ECO.fortress_upgrade(code, u, key(f"m{code}:{level}"), db)):
                    _count(persona, "upgrades", today, 1)
                break
    if s["guild_donate"]:
        from ..models import GuildMember
        if db.scalar(select(GuildMember).where(GuildMember.user_id == persona.user_id)) is not None and \
                (persona.traits or {}).get("loyalty", 0.5) > rng.random():
            from ..social import guilds as GU
            safe("donate", lambda: GU.donate(u, key(f"d{today}"), db))
    if ups or "summon" in log["steps"]:
        set_team(db, persona, best_formation(db, persona, rng))
    from ..social.common import compute_power
    compute_power(db, persona.user_id)
    db.commit()
    log["wallet"] = {k: v for k, v in wallet(db, persona.user_id).items() if v}
    return log


def _after_battle(db: Session, persona: AiPersona, node: CampaignNode, won: bool, rng: random.Random) -> None:
    from . import memory as MEM
    from . import personality as PERS
    from ..social.ai.population import log as alog
    c = dict(persona.counters or {})
    if won:
        c["camp_losses_row"] = 0
        c["camp_cleared"] = int(c.get("camp_cleared", 0)) + 1
        persona.counters = c
        if node.order % 10 == 0:
            MEM.bio_add(db, persona, "milestone", f"Прошёл этап «{node.name}» в кампании")
        alog(db, persona, "campaign", node=node.code, won=True)
    else:
        c["camp_losses_row"] = int(c.get("camp_losses_row", 0)) + 1
        persona.counters = c
        MEM.add(db, persona, "defeat", f"Не прошёл этап «{node.name}» — надо усилить отряд", importance=1)
        if c["camp_losses_row"] >= 3:
            MEM.add(db, persona, "decision", "Меняю тактику после серии поражений в кампании", importance=2)
            strat = (persona.counters or {}).get("strategy", "balanced")
            nxt = {"balanced": "defensive", "defensive": "aggressive", "aggressive": "balanced"}[strat]
            c = dict(persona.counters or {})
            c["strategy"] = nxt
            persona.counters = c
            PERS.evolve(db, persona, "arena_loss")
        alog(db, persona, "campaign", node=node.code, won=False)


def _after_summon(db: Session, persona: AiPersona, r: dict) -> None:
    from . import memory as MEM
    for res in r.get("results", []):
        if res.get("rarity", 0) >= 5 and not res.get("duplicate"):
            h = db.get(Hero, res["hero_code"])
            MEM.add(db, persona, "victory", f"Призвал героя «{h.name if h else res['hero_code']}»", importance=3)
            MEM.bio_add(db, persona, "milestone", f"Призвал легендарного героя «{h.name if h else res['hero_code']}»")


def stats(db: Session) -> dict:
    """Economy monitoring for the admin panel: AI income and spending by reason over the last 24 hours."""
    from datetime import timedelta
    from ..core.db import utcnow
    from ..models import Wallet, WalletTransaction
    since = utcnow() - timedelta(hours=24)
    ai = select(PlayerProfile.user_id).where(PlayerProfile.is_ai.is_(True))
    totals = dict(db.execute(select(Wallet.currency, func.sum(Wallet.balance)).where(Wallet.user_id.in_(ai))
                             .group_by(Wallet.currency)).all())
    flows = db.execute(select(WalletTransaction.reason, WalletTransaction.currency, func.sum(WalletTransaction.delta),
                              func.count()).where(WalletTransaction.user_id.in_(ai), WalletTransaction.created_at >= since)
                       .group_by(WalletTransaction.reason, WalletTransaction.currency)).all()
    battles = db.scalar(select(func.count()).select_from(Battle).where(Battle.user_id.in_(ai), Battle.created_at >= since)) or 0
    return {"balances": {k: int(v or 0) for k, v in totals.items()}, "battles_24h": battles,
            "flows_24h": [{"reason": r, "currency": c, "sum": int(sm or 0), "count": n} for r, c, sm, n in flows]}
