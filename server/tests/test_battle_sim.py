from app.game import data as D
from app.game.battle_sim import hero_stats, make_unit, simulate

H = {h["code"]: h for h in D.HEROES}


def team(side, codes, level):
    return [make_unit(side, i, H[c], hero_stats(H[c], level), level, None) for i, c in enumerate(codes)]


def test_deterministic():
    a = simulate(team(0, ["azamat", "mirgali", "gulnaz"], 3), team(1, ["e_minion", "e_rogue"], 2), 12345)
    b = simulate(team(0, ["azamat", "mirgali", "gulnaz"], 3), team(1, ["e_minion", "e_rogue"], 2), 12345)
    assert a == b
    assert a["result"] in ("victory", "defeat")
    assert a["events"]


def test_strong_team_wins_weak_loses():
    win = simulate(team(0, ["burebai", "aigul", "humai"], 30), team(1, ["e_minion"], 1), 1)
    assert win["result"] == "victory"
    lose = simulate(team(0, ["ilgiz"], 1), team(1, ["e_boss_toratau", "e_mage"], 20), 1)
    assert lose["result"] == "defeat"


def test_starter_team_can_clear_first_node():
    wins = sum(simulate(team(0, D.STARTER_HEROES, 1), team(1, ["e_minion", "e_minion"], 1), s)["result"] == "victory"
               for s in range(50))
    assert wins >= 45, wins


def test_realtime_log_is_time_ordered_and_simultaneous():
    r = simulate(team(0, ["azamat", "mirgali", "zulfiya", "gulnaz", "ramil"], 5),
                 team(1, ["e_warrior", "e_minion", "e_rogue", "e_mage"], 5), 3)
    ts = [e["t"] for e in r["events"]]
    assert ts == sorted(ts)
    assert r["duration"] <= 90.0
    attacks = [e for e in r["events"] if e["type"] in ("attack", "skill")]
    # both sides act inside the same second -> simultaneous combat, not alternating turns
    first_sec = {e["actor"][0] for e in attacks if e["t"] < attacks[0]["t"] + 1.0}
    assert first_sec == {"p", "e"}
    assert all(e["impact"] >= e["t"] for e in attacks)
    assert any(e["type"] == "pos" for e in r["events"])


def test_vip_speeds():
    assert D.battle_speeds(0) == [1, 2]
    assert D.battle_speeds(1) == [1, 2, 4]
    assert D.battle_speeds(5) == [1, 2, 4, 6]
