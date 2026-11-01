"""Interface layout editor: built-in layout, validation (no lock-out), save/version, rollback, delivery to the client."""
import copy

import pytest

ADMIN = "web-admin-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)


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
