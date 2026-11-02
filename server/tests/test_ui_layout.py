"""Interface layout editor: built-in layout, validation (no lock-out), save/version, rollback, delivery to the client."""
import copy

import pytest

ADMIN = "web-admin-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin(monkeypatch, tmp_path):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "content_store_path", tmp_path / "store")  # uploaded maps go to a temp store


H = {"X-Admin-Token": ADMIN}


def test_layout_edit_validate_publish_rollback(client, newplayer):
    assert client.get("/admin/api/game/layout").status_code == 403
    d = client.get("/admin/api/game/layout", headers=H).json()
    assert d["targets"] and "home" in d["icons"] and len(d["blocks"]) == 4
    base = copy.deepcopy(d["default"])
    lay = copy.deepcopy(base)
    # lock-out guard: «Главная» cannot be hidden, unknown button / icon / duplicates rejected
    bad = copy.deepcopy(lay)
    bad["nav"][0]["hidden"] = True
    r = client.post("/admin/api/game/layout", json={"layout": bad}, headers=H)
    assert r.status_code == 400 and "Главная" in r.json()["detail"]["message"]
    for mut in (lambda x: x["nav"].append({"id": "hack"}), lambda x: x["nav"][1].update(icon="nope"),
                lambda x: x["home"]["left"].append(x["home"]["right"][0]),
                lambda x: x["home"]["actions"].append({"id": "equipment"}),
                lambda x: x["home"]["blocks"].pop(), lambda x: x["more"].update(columns=9)):
        b = copy.deepcopy(lay)
        mut(b)
        assert client.post("/admin/api/game/layout", json={"layout": b}, headers=H).status_code == 400
    # a real edit: move «Арена» to the left column, rename the shop button, hide the daily strip, new «Ещё» group
    arena = next(i for i in lay["home"]["right"] if i["id"] == "arena")
    lay["home"]["right"].remove(arena)
    lay["home"]["left"].insert(0, arena)
    lay["home"]["actions"][0]["label"] = "Лавка"
    lay["home"]["blocks"][2]["hidden"] = True
    lay["more"]["groups"].append({"title": "Сражения", "items": [{"id": "raids"}, {"id": "tournaments", "icon": "crown"}]})
    v1 = client.post("/admin/api/game/layout", json={"layout": lay}, headers=H).json()
    assert v1["version"] >= 1 and v1["layout"]["home"]["left"][0]["id"] == "arena"
    assert v1["layout"]["more"]["groups"][-1]["items"][0]["label"] == "Рейды"  # default label filled in
    # the client gets it without login and in the bootstrap
    pub = client.get("/api/v1/client/layout").json()
    assert pub["version"] == v1["version"] and pub["layout"]["home"]["actions"][0]["label"] == "Лавка"
    p = newplayer()
    assert p.get("/player/bootstrap").json()["layout"]["version"] == v1["version"]
    assert client.get("/admin/api/game/layout", headers=H).json()["history"]
    # rollback returns the previous layout with a higher version (clients always move forward)
    rb = client.post("/admin/api/game/layout/rollback", headers=H).json()
    assert rb["version"] > v1["version"] and rb["layout"]["home"]["left"][0]["id"] != "arena"
    rs = client.post("/admin/api/game/layout/reset", headers=H).json()
    assert rs["layout"] == base and rs["version"] > rb["version"]


def test_screen_rules_any_screen_and_where_buttons_lead(client, newplayer):
    """Rules over the real interface of any screen: rename / hide / colour / move / where a button leads; bundled
    interface map; mapper flag gates the upload from the game."""
    import base64
    d = client.get("/admin/api/game/layout", headers=H).json()
    assert "settings" in d["screens"] and "main" in d["screens"]
    lay = d["layout"]
    lay["screens"] = {"more": {"rules": [{"key": "Рейтинг", "kind": "button", "action": "arena", "color": "#ffcc66"},
                                         {"key": "Почта", "kind": "button", "label": "Письма"},
                                         {"key": "Прогресс", "kind": "label", "label": "Развитие"},
                                         {"key": "Пусто", "kind": "button"}]},  # no effect -> dropped
                      "settings": {"rules": [{"key": "Назад", "kind": "button", "action": "home", "move": -1}]}}
    v = client.post("/admin/api/game/layout", json={"layout": lay}, headers=H).json()
    assert len(v["layout"]["screens"]["more"]["rules"]) == 3
    assert client.get("/api/v1/client/layout").json()["layout"]["screens"]["settings"]["rules"][0]["action"] == "home"
    for bad in ({"nowhere": {"rules": []}}, {"more": {"rules": [{"key": "x", "kind": "label", "action": "shop"}]}},
                {"more": {"rules": [{"key": "x", "kind": "button", "action": "equipment"}]}},
                {"more": {"rules": [{"key": "x", "kind": "button", "move": 99}]}},
                {"more": {"rules": [{"key": "x", "kind": "button", "hidden": True}, {"key": "x", "kind": "button", "hidden": True}]}}):
        assert client.post("/admin/api/game/layout", json={"layout": {**lay, "screens": bad}}, headers=H).status_code == 400
    m = client.get("/admin/api/game/layout/map", headers=H).json()
    assert m["screens"]["more"]["elements"] and m["screens"]["more"]["source"] in ("bundled", "uploaded")
    assert client.get("/admin/api/game/layout/map/more.jpg", headers=H).content[:3] == b"\xff\xd8\xff"
    # upload from the game: only a marked mapper
    p = newplayer()
    body = {"screen": "mail", "elements": [{"key": "Забрать всё", "kind": "button", "text": "Забрать всё", "rect": [0.1, 0.2, 0.3, 0.05]}],
            "image_b64": base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 50).decode(), "client": "0.7.8"}
    assert p.post("/client/ui-map", body, key=False).status_code == 403
    uid = p.get("/player/me").json()["profile"]["uralia_id"]
    assert client.post("/admin/api/game/layout/mappers", json={"uralia_id": uid, "on": True}, headers=H).status_code == 200
    assert p.get("/player/me").json()["profile"]["ui_mapper"] is True
    assert p.post("/client/ui-map", body, key=False).json()["elements"] == 1
    mm = client.get("/admin/api/game/layout/map", headers=H).json()
    assert mm["screens"]["mail"]["source"] == "uploaded" and mm["mappers"][0]["uralia_id"] == uid
    client.post("/admin/api/game/layout/mappers", json={"uralia_id": uid, "on": False}, headers=H)
    client.post("/admin/api/game/layout/reset", headers=H)


def test_main_menu_structure_tree_and_required_elements(client):
    d = client.get("/admin/api/game/layout", headers=H).json()
    assert {r["id"] for r in d["required"]} == {"battle", "afk", "quests", "mail", "settings"}
    lay = d["layout"]
    tree = d["tree_from_home"]  # the simple main screen converted 1:1
    assert tree["type"] == "vbox" and [c["type"] for c in tree["children"]] == ["campaign_strip", "hbox", "daily_strip", "hbox"]
    custom = {"type": "vbox", "sep": 12, "children": [
        {"type": "text", "text": "Добро пожаловать!", "size": "title", "align": "center"},
        {"type": "image", "path": "ui/home/banner_1.png", "height": 360},
        {"type": "grid", "columns": 4, "children": [{"type": "tile", "id": "afk", "label": "Дозор", "icon": "afk"},
                                                     {"type": "tile", "id": "quests", "label": "Задания", "icon": "quests"}]},
        {"type": "hbox", "expand": True, "children": [{"type": "squad", "expand": True},
                                                      {"type": "big", "id": "battle", "label": "В бой", "icon": "arena", "color": "#8e1b1b", "ratio": 2}]},
        {"type": "spacer", "size": 24}]}
    v = client.post("/admin/api/game/layout", json={"layout": {**lay, "home": {**lay["home"], "tree": custom}}}, headers=H).json()
    assert v["layout"]["home"]["tree"]["children"][2]["columns"] == 4
    assert client.get("/api/v1/client/layout").json()["layout"]["home"]["tree"]["children"][0]["text"] == "Добро пожаловать!"

    def post(t, more=None):
        L2 = {**lay, "home": {**lay["home"], "tree": t}}
        if more is not None:
            L2["more"] = more
        return client.post("/admin/api/game/layout", json={"layout": L2}, headers=H)
    import copy
    no_afk = copy.deepcopy(custom)
    no_afk["children"][2]["children"].pop(0)
    r = post(no_afk)
    assert r.status_code == 400 and "дозор" in r.json()["detail"]["message"].lower()
    more_afk = copy.deepcopy(lay["more"])
    more_afk["groups"][0]["items"].append({"id": "afk", "label": "Дозор", "icon": "afk"})
    assert post(no_afk, more_afk).status_code == 200  # the patrol moved to «Ещё» — allowed
    no_battle = copy.deepcopy(custom)
    no_battle["children"][3]["children"].pop(1)
    assert post(no_battle).status_code == 200  # «Поход» is still in the bottom bar — enough
    nav_no_camp = [dict(i, hidden=True) if i["id"] == "campaign" else i for i in lay["nav"]]
    r = client.post("/admin/api/game/layout", json={"layout": {**lay, "nav": nav_no_camp, "home": {**lay["home"], "tree": no_battle}}}, headers=H)
    assert r.status_code == 400 and "бой" in r.json()["detail"]["message"].lower()
    for bad in ({"type": "hbox", "children": []},  # root must be a column
                {"type": "vbox", "children": [{"type": "squad"}, {"type": "squad"}]},  # single widgets once
                {"type": "vbox", "children": [{"type": "image", "path": "../etc/x.png"}]},
                {"type": "vbox", "children": [{"type": "script", "code": "x"}]}):
        assert post(bad).status_code == 400
    client.post("/admin/api/game/layout/reset", headers=H)
