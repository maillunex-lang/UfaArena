"""Player, heroes, formation, battles & campaign endpoints."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.db import as_utc, get_db, utcnow
from ..core.deps import CurrentUser, player, run_idempotent
from ..core.errors import GameError
from ..core.idempotency import require_key
from ..game import data as D
from ..game import roster as R
from ..monetization import battlepass as BP
from ..monetization import vip as VIP
from ..monetization.config import cfg as MCFG
from ..monetization.mode import is_test
from ..game.battle_sim import hero_stats, make_unit, power_rating, simulate
from ..models import (
    Battle, CampaignNode, CampaignRegion, Faction, Formation, Hero, HeroClass, PlayerCampaignProgress, PlayerHero,
    PlayerProfile, User,
)
from ..services import (
    afk_preview, grant, hero_dict, hero_view, next_node, node_unlocked, quest_event, spend, team_bonuses, wallet_dict,
)

router = APIRouter(tags=["game"])
BATTLE_TTL = timedelta(minutes=30)


# ------------------------------------------------------------------ player
def _mask_email(e: str | None) -> str:
    if not e or "@" not in e:
        return ""
    name, dom = e.split("@", 1)
    return (name[:2] + "***" if len(name) > 2 else name[:1] + "***") + "@" + dom


def profile_view(p: PlayerProfile, u: User | None = None) -> dict:
    return {"account_kind": (u.kind if u else "guest"), "email_masked": _mask_email(u.email if u else None),
            "uralia_id": p.uralia_id, "nickname": p.nickname, "level": p.level, "exp": p.exp,
            "onboarding_step": p.onboarding_step, "is_ai": p.is_ai, "settings": p.settings or {},
            "age_group": p.age_group, "needs_setup": p.age_group is None and not p.is_ai,
            "vip_level": p.vip_level or 0, "vip_xp": p.vip_xp or 0, "battle_speeds": VIP.battle_speeds(p.vip_level or 0),
            "vip_speed_table": [{"vip": int(k), "speeds": s} for k, s in MCFG()["vip"]["battle_speeds"].items()],
            "created_at": as_utc(p.created_at).isoformat(), "ui_mapper": _ui_mapper(p)}


def _ui_mapper(p: PlayerProfile) -> bool:
    from sqlalchemy.orm import object_session
    db = object_session(p)
    if db is None or p.is_ai:
        return False
    from ..game_editor.layout import is_mapper
    return is_mapper(db, p.user_id)


@router.get("/player/me")
def me(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    return {"user_id": user.id, "profile": profile_view(p, db.get(User, user.id)), "wallet": wallet_dict(db, user.id)}


@router.get("/player/bootstrap")
def bootstrap(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Everything the client needs after login in a single round-trip."""
    p = db.get(PlayerProfile, user.id)
    VIP.daily_activity(db, user.id)  # VIP daily XP + battle pass daily login (once per UTC day)
    db.commit()
    nxt = next_node(db, user.id)
    from .shop import equipped_view
    from ..game_editor import layout as LAYOUT
    return {
        "layout": LAYOUT.get(db),  # admin interface editor: menus and buttons of the main screens
        "cosmetics": equipped_view(db, user.id),
        "test_mode": is_test(db),
        "server_time": utcnow().isoformat(),
        "profile": profile_view(p, db.get(User, user.id)),
        "wallet": wallet_dict(db, user.id),
        "heroes": _player_heroes(db, user.id),
        "formation": _formation(db, user.id).slots,
        "campaign": {"next_node": nxt.code if nxt else None,
                     "cleared": list(db.scalars(select(PlayerCampaignProgress.node_code)
                                               .where(PlayerCampaignProgress.user_id == user.id)))},
        "afk": afk_preview(db, p),
        "rarities": D.RARITIES,
    }


class OnboardingIn(BaseModel):
    step: int = Field(ge=0, le=100)


@router.post("/player/onboarding")
def onboarding(body: OnboardingIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    if body.step > p.onboarding_step:  # monotonic
        p.onboarding_step = body.step
    db.commit()
    return {"onboarding_step": p.onboarding_step}


class SetupIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=3, max_length=20, pattern=r"^[\w\- А-Яа-яЁё]+$")
    adult: bool


@router.post("/player/setup")
def player_setup(body: SetupIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Hero creation window (decision D-C1): nickname + "I am 18 or older". Minors never get private messages or
    adult content from AI residents. Can be changed later in the settings."""
    from ..social.ai.control import player_prefs
    from ..social.chat import contains_bad
    p = db.get(PlayerProfile, user.id)
    if body.nickname:
        if contains_bad(body.nickname):
            raise GameError("bad_nickname", "Никнейм не прошёл фильтр")
        p.nickname = body.nickname.strip()
    first = p.age_group is None
    p.age_group = "adult" if body.adult else "minor"
    p.age_set_at = utcnow()
    prefs = player_prefs(p)
    if not body.adult:
        prefs["adult_content"] = False
    elif first or "adult_content" not in (p.ai_prefs or {}):
        prefs["adult_content"] = True  # adults get adult AI content by default (can switch it off in the settings)
    p.ai_prefs = prefs
    audit(db, user.id, "player.setup", age_group=p.age_group)
    db.commit()
    return {"profile": profile_view(p, db.get(User, user.id))}


class NicknameIn(BaseModel):
    nickname: str = Field(min_length=3, max_length=20, pattern=r"^[\w\- А-Яа-яЁё]+$")


@router.post("/player/nickname")
def nickname(body: NicknameIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    p.nickname = body.nickname.strip()
    db.commit()
    return {"nickname": p.nickname}


class SettingsIn(BaseModel):
    graphics_quality: str = Field(default="auto", pattern="^(auto|low|medium|high)$")
    music_volume: float = Field(default=0.8, ge=0, le=1)
    sfx_volume: float = Field(default=0.9, ge=0, le=1)
    battle_speed: int = Field(default=1, ge=1, le=6)


@router.post("/player/settings")
def save_settings(body: SettingsIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    p = db.get(PlayerProfile, user.id)
    p.settings = body.model_dump()
    db.commit()
    return {"settings": p.settings}


# ------------------------------------------------------------------ heroes
@router.get("/heroes")
def heroes_catalog(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return {
        "factions": [{"code": f.code, "name": f.name, "description": f.description, "is_rare": f.is_rare,
                      "strong_against": f.strong_against, "emblem": f.emblem, "color": f.color, "accent": f.accent,
                      "playable": f.playable} for f in db.scalars(select(Faction))],
        "faction_rules": R.faction_rules(),
        "classes": [{"code": c.code, "name": c.name, "role": c.role} for c in db.scalars(select(HeroClass))],
        "heroes": [{"code": h.code, "name": h.name, "title": h.title, "faction": h.faction_code,
                    "class": h.class_code, "rarity": h.rarity, "model": h.model, "skill": h.skill, "lore": h.lore,
                    "is_enemy": h.is_enemy, "summonable": h.summonable, "role": h.role or "",
                    "role_name": (h.extra or {}).get("role_name", ""),
                    "appearance": (h.extra or {}).get("appearance", ""),
                    "personality": (h.extra or {}).get("personality", ""),
                    "crit": (h.extra or {}).get("crit", 0.12), "crit_dmg": (h.extra or {}).get("crit_dmg", 1.5),
                    "base": {"hp": h.base_hp, "atk": h.base_atk, "def": h.base_def, "spd": h.base_spd},
                    "growth": (h.extra or {}).get("growth", {}),
                    "kit": h.kit or R.legacy_kit(h.skill or {}, h.class_code, h.rarity)}
                   for h in db.scalars(select(Hero).order_by(Hero.rarity, Hero.code))
                   if not (h.extra or {}).get("disabled") or h.code in _owned_codes(db, user.id)],
        "summons": R.summons(),
    }


def _owned_codes(db: Session, user_id: str) -> set[str]:
    return set(db.scalars(select(PlayerHero.hero_code).where(PlayerHero.user_id == user_id)))


def _player_heroes(db: Session, user_id: str) -> list[dict]:
    b = team_bonuses(db, user_id)
    rows = db.scalars(select(PlayerHero).where(PlayerHero.user_id == user_id))
    return sorted((hero_view(ph, b) for ph in rows), key=lambda h: (-h["power"], h["hero_code"]))


@router.get("/player/heroes")
def player_heroes(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return {"heroes": _player_heroes(db, user.id)}


@router.post("/player/heroes/{hero_id}/level-up")
def level_up(hero_id: str, user: CurrentUser = Depends(player), key: str = Depends(require_key),
             db: Session = Depends(get_db)):
    def do():
        ph = db.get(PlayerHero, hero_id)
        if ph is None or ph.user_id != user.id:
            raise GameError("not_found", "Герой не найден", 404)
        if ph.level >= D.LEVEL_CAP_MVP:
            raise GameError("max_level", "Достигнут максимальный уровень")
        spend(db, user.id, D.level_up_cost(ph.level), "hero_level_up", ph.id)
        ph.level += 1
        quest_event(db, user.id, "hero_level_up")
        return {"hero": hero_view(ph, team_bonuses(db, user.id)), "wallet": wallet_dict(db, user.id)}

    return run_idempotent(db, user.id, key, "hero_level_up", {"hero_id": hero_id}, do)


# ------------------------------------------------------------------ formation
def _formation(db: Session, user_id: str) -> Formation:
    f = db.get(Formation, (user_id, "campaign"))
    if f is None:
        f = Formation(user_id=user_id, kind="campaign", slots=[None] * 5)
        db.add(f)
        db.flush()
    return f


class FormationIn(BaseModel):
    slots: list[str | None] = Field(min_length=5, max_length=5)


@router.get("/formation")
def get_formation(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    return {"slots": _formation(db, user.id).slots, "rows": {"front": [0, 1], "back": [2, 3, 4]}}


@router.post("/formation")
def set_formation(body: FormationIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    ids = [s for s in body.slots if s]
    if not ids:
        raise GameError("empty_formation", "Нужен хотя бы один герой")
    if len(ids) != len(set(ids)):
        raise GameError("duplicate_hero", "Герой не может стоять в двух слотах")
    owned = set(db.scalars(select(PlayerHero.id).where(PlayerHero.user_id == user.id, PlayerHero.id.in_(ids))))
    if owned != set(ids):
        raise GameError("not_owned", "Можно ставить только своих героев", 403)
    f = _formation(db, user.id)
    f.slots = list(body.slots)
    db.commit()
    return {"slots": f.slots}


# ------------------------------------------------------------------ battles & campaign
FACTION_ADV = R.advantage()


def _team_units(db: Session, user_id: str, slots: list[str | None], extra: dict | None = None):
    b = dict(team_bonuses(db, user_id))
    for k, v in (extra or {}).items():
        if k in ("atk_pct", "hp_pct"):
            b[k] = b.get(k, 0) + v
    units, snap = [], []
    for slot, pid in enumerate(slots):
        if not pid:
            continue
        ph = db.get(PlayerHero, pid)
        if ph is None or ph.user_id != user_id:
            raise GameError("not_owned", "Отряд содержит чужого героя", 403)
        hd = hero_dict(ph.hero)
        st = hero_stats(hd, ph.level, ph.stars, **b)
        unit = make_unit(0, slot, hd, st, ph.level, FACTION_ADV.get(hd["faction_code"]))
        unit.skill_level = 1 + ph.stars
        units.append(unit)
        snap.append({"slot": slot, "player_hero_id": pid, "hero_code": hd["code"], "level": ph.level,
                     "stars": ph.stars, "power": power_rating(st)})
    if not units:
        raise GameError("empty_formation", "Нужен хотя бы один герой")
    return units, snap


def _enemy_units(db: Session, node: CampaignNode):
    from ..social.events import region_status
    add = 2 if region_status(db, node.region_code) == "scorched" else 0  # world-event consequence
    out = []
    for e in node.enemies:
        hd = hero_dict(db.get(Hero, e["hero_code"]))
        st = hero_stats(hd, e["level"] + add)
        out.append(make_unit(1, e["slot"], hd, st, e["level"] + add, FACTION_ADV.get(hd["faction_code"])))
    return out


class BattleIn(BaseModel):
    node_id: str = Field(max_length=32)
    slots: list[str | None] | None = Field(default=None, min_length=5, max_length=5)


@router.post("/battles/validate")
def battle_validate(body: BattleIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    """Validates node + squad, runs the authoritative simulation and returns the replay log."""
    node = db.get(CampaignNode, body.node_id)
    if node is None:
        raise GameError("not_found", "Узел кампании не найден", 404)
    if not node_unlocked(db, user.id, node):
        raise GameError("node_locked", "Сначала пройдите предыдущий этап", 403)
    slots = body.slots or _formation(db, user.id).slots
    from ..social.friends import consume_blessing
    from ..social.guilds import guild_bonuses
    extra = {k: v for k, v in guild_bonuses(db, user.id).items() if k in ("atk_pct", "hp_pct")}
    bless = consume_blessing(db, user.id)  # "Благословение друга" from friend help
    extra["atk_pct"] = extra.get("atk_pct", 0) + bless
    team, snap = _team_units(db, user.id, slots, extra)
    seed = secrets.randbits(48)
    sim = simulate(team, _enemy_units(db, node), seed)
    sim["bonuses"] = {"guild": {k: round(v, 3) for k, v in extra.items()}, "friend_blessing": bless}
    battle = Battle(user_id=user.id, node_code=node.code, seed=seed, team_snapshot=snap, result=sim["result"],
                    turns=sim["rounds"])
    db.add(battle)
    db.flush()
    quest_event(db, user.id, "battle_fought")
    BP.add_xp(db, user.id, "battle_fought")
    from ..social import progression as SP
    SP.on(db, user.id, "battle_win" if sim["result"] == "victory" else "battle_loss", ref=battle.id)
    db.commit()
    return {"battle_id": battle.id, "node": _node_view(node, True, False), "simulation": sim}


class CompleteIn(BaseModel):
    battle_id: str = Field(max_length=36)


@router.post("/campaign/{node_id}/complete")
def campaign_complete(node_id: str, body: CompleteIn, user: CurrentUser = Depends(player),
                      key: str = Depends(require_key), db: Session = Depends(get_db)):
    def do():
        battle = db.get(Battle, body.battle_id, with_for_update=True)
        if battle is None or battle.user_id != user.id or battle.node_code != node_id:
            raise GameError("not_found", "Бой не найден", 404)
        if battle.status != "simulated":
            raise GameError("already_completed", "Награда за этот бой уже получена", 409)
        if utcnow() - as_utc(battle.created_at) > BATTLE_TTL:
            battle.status = "expired"
            db.commit()
            raise GameError("battle_expired", "Бой устарел, начните заново", 410)
        battle.status, battle.completed_at = "completed", utcnow()
        node = db.get(CampaignNode, node_id)
        rewards: dict = {}
        first_clear = False
        prof = db.get(PlayerProfile, user.id)
        lvl_before, exp_gained = prof.level, 0
        if battle.result == "victory":
            rewards = dict(node.rewards)
            if db.get(PlayerCampaignProgress, (user.id, node_id)) is None:
                first_clear = True
                db.add(PlayerCampaignProgress(user_id=user.id, node_code=node_id, best_turns=battle.turns))
                for k, v in node.first_clear_rewards.items():
                    rewards[k] = rewards.get(k, 0) + v
                db.flush()
                from ..services import cleared_count
                quest_event(db, user.id, "campaign_clear", absolute=cleared_count(db, user.id))
                BP.add_xp(db, user.id, "campaign_clear")
            grant(db, user.id, rewards, "campaign_reward", battle.id)
            p = db.get(PlayerProfile, user.id)
            from ..services import building_levels
            from .caravan import leader_bonus
            lead_kind, lead_val = leader_bonus(db, user.id)
            exp_mult = 1 + 0.05 * (building_levels(db, user.id).get("library", 1) - 1) + (lead_val if lead_kind == "exp" else 0)
            exp_gained = int((40 + 10 * node.order) * exp_mult)
            p.exp += exp_gained
            while p.exp >= 100 * p.level:
                p.exp -= 100 * p.level
                p.level += 1
        audit(db, user.id, "campaign.complete", node=node_id, result=battle.result, rewards=rewards)
        nxt = next_node(db, user.id)
        from ..services import cleared_count, ordered_nodes
        return {"result": battle.result, "rewards": rewards, "first_clear": first_clear,
                "wallet": wallet_dict(db, user.id), "next_node": nxt.code if nxt else None,
                # result screen statistics: player experience, level-ups and campaign progress
                "exp_gained": exp_gained, "level": prof.level, "exp": prof.exp, "level_up": prof.level > lvl_before,
                "campaign_progress": {"cleared": cleared_count(db, user.id), "total": len(ordered_nodes(db))}}

    return run_idempotent(db, user.id, key, f"campaign_complete:{node_id}", {"battle_id": body.battle_id}, do)


def _node_view(n: CampaignNode, unlocked: bool, cleared: bool) -> dict:
    return {"code": n.code, "order": n.order, "name": n.name, "territory": n.territory, "real_place": n.real_place,
            "map_pos": n.map_pos, "is_boss": n.is_boss, "rewards": n.rewards,
            "first_clear_rewards": n.first_clear_rewards, "story": n.story, "unlocked": unlocked,
            "cleared": cleared, "enemies": n.enemies}


@router.get("/campaign")
def campaign(user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    cleared = set(db.scalars(select(PlayerCampaignProgress.node_code)
                             .where(PlayerCampaignProgress.user_id == user.id)))
    from ..services import ordered_nodes
    flat = ordered_nodes(db)
    prev_cleared = {n.code: (i == 0 or flat[i - 1].code in cleared) for i, n in enumerate(flat)}
    regions = []
    from ..game_editor.overrides import hidden_regions
    hid_r = hidden_regions(db)
    from ..game_editor.overrides import world_positions
    world_xy = world_positions(db)
    for r in db.scalars(select(CampaignRegion).order_by(CampaignRegion.order)):
        if r.code in hid_r:
            continue
        nodes = [n for n in flat if n.region_code == r.code]
        from ..social.events import region_status
        regions.append({"code": r.code, "order": r.order, "name": r.name, "real_place": r.real_place,
                        "map_xy": world_xy.get(r.code),
                        "description": r.description, "world_status": region_status(db, r.code),
                        "nodes": [_node_view(n, prev_cleared[n.code], n.code in cleared) for n in nodes]})
    return {"regions": regions}
