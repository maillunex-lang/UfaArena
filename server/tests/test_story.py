"""Lore stage S2: story choices are server-authoritative, one-time, gated by progress and set flags."""


def clear(p, code):
    """Marks a stage as cleared directly (battle outcomes are covered by other tests)."""
    from app.core.db import get_db
    from app.models import PlayerCampaignProgress
    gen = get_db()
    db = next(gen)
    try:
        if db.get(PlayerCampaignProgress, (p.tokens["user_id"], code)) is None:
            db.add(PlayerCampaignProgress(user_id=p.tokens["user_id"], node_code=code, best_turns=1))
        db.commit()
    finally:
        gen.close()


def test_story_choices_rules_and_flags(newplayer):
    p = newplayer()
    st = p.get("/story/state").json()
    ids = {c["id"] for c in st["choices"]}
    assert {"prologue_timer", "prologue_voice", "prologue_camp"} <= ids and st["flags"] == {}
    # unknown choice / option
    assert p.post("/story/choice", {"choice_id": "nope", "option": "x"}).status_code == 404
    assert p.post("/story/choice", {"choice_id": "prologue_timer", "option": "fly"}).status_code == 400
    # gated by campaign progress: the bor scene comes after the river crossing (1-1)
    r = p.post("/story/choice", {"choice_id": "prologue_timer", "option": "followed"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "choice_locked"
    clear(p, "1-1")
    r = p.post("/story/choice", {"choice_id": "prologue_timer", "option": "followed"})
    assert r.status_code == 200 and r.json()["flags"]["timer_path"] == "followed"
    # the same answer again is accepted (replayed scene), a different one is refused
    assert p.post("/story/choice", {"choice_id": "prologue_timer", "option": "followed"}).status_code == 200
    r = p.post("/story/choice", {"choice_id": "prologue_timer", "option": "stayed"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_chosen"
    st = p.get("/story/state").json()
    made = {c["id"]: c["made"] for c in st["choices"]}
    assert made["prologue_timer"] == "followed" and made["prologue_voice"] is None
    avail = {c["id"]: c["available"] for c in st["choices"]}
    assert avail["prologue_timer"] and not avail["prologue_voice"]
    assert st["flags"] == {"timer_path": "followed"}


def test_prologue_scenario_sets_all_flags(newplayer):
    p = newplayer()
    for code in ["1-1", "1-2", "1-3"]:
        clear(p, code)
    assert p.post("/story/choice", {"choice_id": "prologue_timer", "option": "stayed"}).status_code == 200
    assert p.post("/story/choice", {"choice_id": "prologue_voice", "option": "reject"}).status_code == 200
    assert p.post("/story/choice", {"choice_id": "prologue_camp", "option": "nobody"}).status_code == 403  # 1-6 not yet
    st = p.get("/story/state").json()
    assert st["flags"] == {"timer_path": "stayed", "voice_tone": "reject"}


def test_campaign_story_lines_reference_known_choices_and_flags():
    """Content check: every choice marker exists, every condition uses a flag/value that some option sets."""
    from app.game import data as D
    from app.modules.story import choices
    ch = choices()
    settable = {(k, v) for c in ch.values() for o in c["options"].values() for k, v in o["flags"].items()}
    for n in D.NODES:
        for line in n.get("story", []):
            if "choice" in line:
                assert line["choice"] in ch, (n["code"], line)
                assert ch[line["choice"]]["scene"] == n["code"]
            for k, v in (line.get("if") or {}).items():
                assert (k, v) in settable, (n["code"], k, v)
