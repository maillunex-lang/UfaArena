"""ZIP patches: dry run writes nothing, apply is all-or-nothing, rollback of the last patch, AI task templates for every
setting type, ZIP safety (paths, extensions), JSON pasted from an AI chat."""
import io
import json
import struct
import zipfile
import zlib

import pytest

ADMIN = "web-admin-token-0123456789abcdef"
H = {"X-Admin-Token": ADMIN}


@pytest.fixture(autouse=True)
def _admin(monkeypatch, tmp_path):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "content_store_path", tmp_path / "store")


def zp(doc, files=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("patch.json", json.dumps(doc, ensure_ascii=False))
        for k, v in (files or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


def png(w, h):
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def post(client, path, data):
    return client.post("/admin/api/game/patches/" + path, content=data, headers={**H, "Content-Type": "application/octet-stream"})


def test_every_setting_has_a_task_template(client):
    types = client.get("/admin/api/game/patches/types", headers=H).json()["types"]
    assert {t["type"] for t in types} >= {"hero", "region", "node", "node_order", "map", "ui_layout", "ai_settings",
                                          "ai_switches", "shop_product", "art"}
    for t in types:
        tg = client.get(f"/admin/api/game/patches/targets?type={t['type']}", headers=H).json()["targets"]
        assert tg, t
        one = next((x["id"] for x in tg if not x["id"].startswith(("*", "region:"))), tg[0]["id"])
        tk = client.get(f"/admin/api/game/patches/task?type={t['type']}&id={one}", headers=H).json()
        assert "{{WISH}}" in tk["prompt"] and "uralia-patch/1" in tk["prompt"] and tk["patch"]["changes"]
        z = client.get(f"/admin/api/game/patches/template?type={t['type']}&id={one}&wish=Сделай лучше", headers=H)
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert "patch.json" in names and "AI_TASK.md" in names
        if t["type"] != "art":  # the exported current state is itself a valid patch (round trip)
            r = post(client, "check", zipfile.ZipFile(io.BytesIO(z.content)).read("patch.json"))
            assert r.status_code == 200 and r.json()["ok"], (t["type"], r.json())


def test_check_apply_rollback_hero_layout_ai(client):
    hero = client.get("/admin/api/game/heroes", headers=H).json()["items"][0]
    code, atk = hero["code"], hero["base_atk"]
    flirt0 = client.get("/admin/api/ai/settings/outreach", headers=H).json()["settings"]["flirt_per_player_week"]
    doc = {"format": "uralia-patch/1", "title": "Тест", "author": "Claude", "changes": [
        {"type": "hero", "code": code, "fields": {"base_atk": atk + 7}},
        {"type": "hero", "code": "patch_hero_x", "fields": {"name": "Патчевый", "faction_code": hero["faction_code"],
         "class_code": hero["class_code"], "rarity": 3, "base_hp": 1000, "base_atk": 100, "base_def": 50, "base_spd": 100}},
        {"type": "ui_layout", "merge": {"home": {"actions": [{"id": "battle", "label": "В поход!", "icon": "arena",
                                                              "color": "#8e1b1b", "ratio": 2}]}}},
        {"type": "ai_settings", "section": "outreach", "values": {"flirt_per_player_week": 2 if flirt0 != 2 else 4}},
        {"type": "ai_switches", "values": {"arena": False}},
    ]}
    r = post(client, "check", zp(doc)).json()
    assert r["ok"], r
    d0 = r["changes"][0]["diff"]
    assert d0 == [{"field": "base_atk", "before": atk, "after": atk + 7}]
    assert r["changes"][1]["new"] is True
    # dry run wrote nothing
    assert next(h for h in client.get("/admin/api/game/heroes", headers=H).json()["items"] if h["code"] == code)["base_atk"] == atk
    assert client.get("/api/v1/client/layout").json()["layout"]["home"]["actions"][0]["label"] != "В поход!"
    a = client.post("/admin/api/game/patches/apply", content=json.dumps(doc), headers=H).json()  # bare JSON works too
    assert a["applied"] == 5
    assert client.get("/admin/api/ai/settings/outreach", headers=H).json()["settings"]["flirt_per_player_week"] != flirt0
    assert next(h for h in client.get("/admin/api/game/heroes", headers=H).json()["items"] if h["code"] == code)["base_atk"] == atk + 7
    assert client.get("/api/v1/client/layout").json()["layout"]["home"]["actions"][0]["label"] == "В поход!"
    hist = client.get("/admin/api/game/patches", headers=H).json()["items"]
    assert hist[0]["id"] == a["id"] and hist[0]["status"] == "applied"
    rb = client.post("/admin/api/game/patches/rollback", json={"id": a["id"]}, headers=H)
    assert rb.status_code == 200
    heroes = {h["code"]: h for h in client.get("/admin/api/game/heroes", headers=H).json()["items"]}
    assert heroes[code]["base_atk"] == atk and "patch_hero_x" not in heroes
    assert client.get("/api/v1/client/layout").json()["layout"]["home"]["actions"][0]["label"] != "В поход!"
    assert client.get("/admin/api/ai/settings/outreach", headers=H).json()["settings"]["flirt_per_player_week"] == flirt0
    assert client.get("/admin/api/game/patches", headers=H).json()["items"][0]["status"] == "rolled_back"


def test_all_or_nothing_and_errors(client):
    hero = client.get("/admin/api/game/heroes", headers=H).json()["items"][0]
    doc = {"changes": [{"type": "hero", "code": hero["code"], "fields": {"base_atk": hero["base_atk"] + 3}},
                       {"type": "hero", "code": hero["code"], "fields": {"rarity": 99}}]}
    r = post(client, "check", zp(doc)).json()
    assert not r["ok"] and r["changes"][0]["ok"] and "rarity" in r["changes"][1]["error"]
    bad = post(client, "apply", zp(doc))
    assert bad.status_code == 400 and "№2" in bad.json()["detail"]["message"]
    assert next(h for h in client.get("/admin/api/game/heroes", headers=H).json()["items"]
                if h["code"] == hero["code"])["base_atk"] == hero["base_atk"]  # nothing applied
    # format / zip safety
    assert post(client, "check", b"not json").status_code == 400
    assert post(client, "check", zp({"changes": [{"type": "rm -rf"}]})).status_code == 400
    assert post(client, "check", zp(doc, {"files/x.exe": b"MZ"})).status_code == 400
    assert post(client, "check", zp(doc, {"../evil.png": png(2, 2)})).status_code == 400
    # JSON pasted from an AI chat inside ``` fences, wrapped folder in a zip
    fenced = ("```json\n" + json.dumps({"format": "uralia-patch/1", "changes": doc["changes"][:1]}) + "\n```").encode()
    assert post(client, "check", fenced).json()["ok"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("uralia_patch/patch.json", json.dumps({"changes": doc["changes"][:1]}))
    assert post(client, "check", buf.getvalue()).json()["ok"]


def test_art_patch_and_rollback(client):
    cat = client.get("/admin/api/web/art", headers=H).json()
    slot = next(s for s in cat["sections"] if s["id"] == "icons")["slots"][0]
    w, h = (int(x) for x in slot["size"].split("×"))
    doc = {"changes": [{"type": "art", "path": slot["path"], "file": "files/icon.png"}]}
    assert not post(client, "check", zp(doc)).json()["ok"]  # file missing
    r = post(client, "check", zp(doc, {"files/icon.png": png(w, h)})).json()
    assert r["ok"] and r["changes"][0]["diff"]
    assert client.get("/admin/api/web/art/file?path=" + slot["path"], headers=H).status_code == 404  # dry run
    a = post(client, "apply", zp(doc, {"files/icon.png": png(w, h)})).json()
    assert client.get("/admin/api/web/art/file?path=" + slot["path"], headers=H).status_code == 200
    client.post("/admin/api/game/patches/rollback", json={"id": a["id"]}, headers=H)
    assert client.get("/admin/api/web/art/file?path=" + slot["path"], headers=H).status_code == 404
