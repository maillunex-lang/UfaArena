"""HERO FORGE roster: 3 factions, 12 heroes with exact ids/classes/rarities, and every ability works in battle."""
import pytest

from app.game import data as D
from app.game import roster as R
from app.game.battle_sim import hero_stats, make_unit, simulate, faction_synergy

H = {h["code"]: h for h in D.HEROES}
SPEC = {  # id: (faction, class, rarity) — from the integration brief table
    "arslan_kara": ("stone_sky", "warrior", 4), "bai_tash": ("stone_sky", "guardian", 5),
    "safariy": ("stone_sky", "mage", 2), "ai_tulgan": ("stone_sky", "healer", 3),
    "yurek": ("living_kurai", "ranger", 1), "sumbel": ("living_kurai", "summoner", 4),
    "ak_bure": ("living_kurai", "assassin", 5), "tan_chechek": ("living_kurai", "hybrid", 2),
    "vargat": ("ashen_reach", "warrior", 3), "morai": ("ashen_reach", "mage", 6),
    "zarkhan": ("ashen_reach", "ranger", 4), "ur_kaan": ("ashen_reach", "hybrid", 6),
}
ADV = R.advantage()


def team(side, codes, level):
    return [make_unit(side, i, H[c], hero_stats(H[c], level), level, ADV.get(H[c]["faction_code"]))
            for i, c in enumerate(codes)]


def battle(a, b, level=20, seed=5):
    return simulate(team(0, a, level), team(1, b, level), seed)


def names(r, side=None):
    out = set()
    for e in r["events"]:
        if e["type"] in ("skill", "ultimate", "mechanic") and (side is None or e["actor"][0] == side):
            out.add(e["name"])
    return out


def test_factions_and_roster_spec():
    assert [f["code"] for f in R.factions()] == ["stone_sky", "living_kurai", "ashen_reach"]
    assert {f["name"] for f in R.factions()} == {"Каменное Небо", "Живой Курай", "Пепельный Предел"}
    for code, (fac, cls, rar) in SPEC.items():
        h = H[code]
        assert (h["faction_code"], h["class_code"], h["rarity"]) == (fac, cls, rar), code
        kit = h["kit"]
        assert kit["basic"]["effects"] and len(kit["skills"]) == 2 and kit["ultimate"]["effects"]
        assert kit["passive"]["name"] and kit["mechanic"]["name"]
        assert h["lore"] and h["extra"]["appearance"] and h["extra"]["role_name"]


def test_legacy_heroes_moved_to_official_factions():
    official = {"stone_sky", "living_kurai", "ashen_reach"}
    for h in D.HEROES:
        if not h.get("is_enemy"):
            assert h["faction_code"] in official, h["code"]


@pytest.fixture(scope="module")
def mirror():
    r1 = battle(["arslan_kara", "bai_tash", "safariy", "ai_tulgan", "yurek"],
                ["vargat", "ur_kaan", "morai", "zarkhan", "ak_bure"])
    r2 = battle(["sumbel", "tan_chechek", "ak_bure", "yurek", "bai_tash"],
                ["arslan_kara", "vargat", "ai_tulgan", "zarkhan", "ur_kaan"], seed=11)
    return r1, r2


@pytest.mark.parametrize("code", list(SPEC))
def test_every_hero_casts_both_skills_and_ultimate(code):
    allies = [code] + [c for c in ("bai_tash", "ai_tulgan") if c != code] + (["sumbel"] if code in ("bai_tash", "ai_tulgan") else [])
    foes = ["e_warrior", "e_minion", "e_rogue", "e_mage"]
    r = simulate(team(0, allies, 20), [make_unit(1, i, H[c], hero_stats(H[c], 18), 18, None) for i, c in enumerate(foes)], 3)
    seen = names(r, "p")
    kit = H[code]["kit"]
    for sk in kit["skills"]:
        assert sk["name"] in seen, f"{code}: skill {sk['name']} never cast"
    assert kit["ultimate"]["name"] in seen, f"{code}: ultimate never cast"


def test_unique_mechanics_trigger(mirror):
    seen = names(mirror[0]) | names(mirror[1])
    for mech in ["Клятва перевала", "Ритм рун", "Мелодия перевала", "Цветение", "Охота стаи"]:
        assert mech in seen, mech
    events = mirror[0]["events"] + mirror[1]["events"]
    redirects = [r for e in events if e["type"] in ("attack", "skill", "ultimate") for t in e["targets"]
                 for r in t.get("redirect", [])]
    assert redirects, "Bai-Tash / root guardian never intercepted damage"
    summons = {e["unit"]["code"] for e in events if e["type"] == "summon"}
    assert {"root_guardian", "dragon_echo_small", "dragon_echo"} <= summons, summons
    applied = [a for e in events for t in e.get("targets", []) for a in t.get("applied", [])]
    assert any(a.startswith("mark:trail") for a in applied)       # Yurek
    assert any(a.startswith("mark:ash") for a in applied)         # Zarkhan
    assert any(a.startswith("mark:rift") for a in applied)        # Morai
    assert any(a == "heal_received-" for a in applied)            # Zarkhan heal cut
    assert any(a == "taunt" for a in applied)                     # Bai-Tash ultimate
    removed = [x for e in events for t in e.get("targets", []) for x in t.get("removed", [])]
    assert removed                                                 # Vargat dispel / cleanses
    assert any(t.get("delayed") for e in events for t in e.get("targets", []))  # Morai / Safariy / Ak-Bure


def test_control_is_bounded():
    r = battle(["morai", "safariy", "sumbel", "ak_bure", "yurek"], ["bai_tash", "arslan_kara", "vargat", "ur_kaan", "ai_tulgan"])
    delays = {}
    for e in r["events"]:
        for t in e.get("targets", []):
            if t.get("delayed"):
                delays.setdefault(t["uid"], []).append(e["t"])
    for uid, ts in delays.items():
        ts.sort()
        # no unit is re-delayed within the immunity window (no infinite control)
        assert all(b - a >= 0.99 for a, b in zip(ts, ts[1:])), (uid, ts)


def test_faction_synergy():
    fac, bonus = faction_synergy(team(0, ["vargat", "morai", "zarkhan", "ur_kaan"], 1))
    assert fac == "ashen_reach" and bonus == pytest.approx(0.12)
    assert faction_synergy(team(0, ["vargat", "yurek"], 1))[1] == 0


def test_deterministic_with_kits():
    a = battle(["arslan_kara", "sumbel", "morai"], ["ur_kaan", "ak_bure"], seed=99)
    b = battle(["arslan_kara", "sumbel", "morai"], ["ur_kaan", "ak_bure"], seed=99)
    assert a == b
