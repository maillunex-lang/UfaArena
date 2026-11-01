"""Web admin panel: overview, release, events, mail, admin chat, art upload/publish, APK upload."""
import struct
import zlib

import pytest

ADMIN = "web-admin-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _admin(monkeypatch, tmp_path):
    monkeypatch.setenv("URALIA_ADMIN_TOKEN", ADMIN)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "downloads_path", tmp_path / "dl")
    monkeypatch.setattr(get_settings(), "content_store_path", tmp_path / "store")


def H(extra=None):
    return {"X-Admin-Token": ADMIN, "X-Admin-Name": "%D0%92%D0%BB%D0%B0%D0%B4", **(extra or {})}


def png(w, h):
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_page_and_auth(client):
    assert "админ-панель" in client.get("/admin").text
    assert client.get("/admin/shop").status_code == 200
    assert client.get("/admin/api/web/overview").status_code == 403
    d = client.get("/admin/api/web/overview", headers=H()).json()
    assert "players" in d and "jobs" in d


def test_release_and_apk(client):
    r = client.post("/admin/api/web/apk?name=uralia-9.1.0.apk", content=b"PK" + b"x" * 1000,
                    headers=H({"Content-Type": "application/octet-stream"}))
    assert r.status_code == 200 and r.json()["size"] == 1002
    assert client.post("/admin/api/web/apk?name=bad.apk", content=b"nope", headers=H()).status_code == 400
    r = client.post("/admin/api/web/release", json={"version": "9.1.0", "min_version": "0.5.0", "title": "Тест",
                                                    "notes": ["Новое"], "file": "uralia-9.1.0.apk", "url": None}, headers=H())
    assert r.status_code == 200
    rel = client.get("/api/v1/client/release?version=0.6.0").json()
    assert rel["latest"] == "9.1.0" and rel["update_available"] and rel["notes"] == ["Новое"]
    assert client.get("/download/apk").content.startswith(b"PK")
    from app.core.db import get_db
    from app.models import ServerSetting
    gen = get_db()
    db = next(gen)
    db.delete(db.get(ServerSetting, "release"))  # keep other tests independent of this override
    db.commit()
    gen.close()


def test_events_raids_tournaments_mail_chat(client, newplayer):
    p = newplayer()
    d = client.get("/admin/api/web/events", headers=H()).json()
    assert d["templates"] and d["tournament_templates"]
    r = client.post("/admin/api/web/events/start", json={"template": "darkness_invasion", "hours": 5, "goal": 5000}, headers=H())
    eid = r.json()["id"]
    assert any(e["id"] == eid for e in p.get("/events").json()["active"])
    assert client.post(f"/admin/api/web/events/{eid}/finish", headers=H()).json()["outcome"] == "failure"
    assert client.post("/admin/api/web/raids/respawn", json={"kind": "world"}, headers=H()).status_code == 200
    tid = client.post("/admin/api/web/tournaments/create", json={"template": "weekly_open", "reg_hours": 5}, headers=H()).json()["id"]
    assert p.post(f"/tournaments/{tid}/register", {}, key=False).status_code == 200
    m = client.post("/admin/api/web/mail-all", json={"title": "Подарок", "body": "Спасибо!", "rewards": {"crystals": 50, "hack": 9}},
                    headers=H()).json()
    assert m["recipients"] >= 1
    mail = p.get("/mail").json()
    items = mail.get("items", mail.get("mail", []))
    assert any(x.get("title") == "Подарок" for x in items)
    assert client.post("/admin/api/web/chat", json={"channel": "global", "text": "Сервер обновлён!"}, headers=H()).status_code == 200
    msgs = p.get("/chat/messages?channel=global").json()["messages"]
    assert any(x["system"] and x["text"].startswith("📢 Администрация") for x in msgs)
    assert client.post("/admin/api/web/chat", json={"channel": "dm:a:b", "text": "x"}, headers=H()).status_code == 400


def test_art_upload_and_publish(client):
    cat = client.get("/admin/api/web/art", headers=H()).json()
    ids = {s["id"] for s in cat["sections"]}
    assert {"heroes", "icons", "chat", "screens", "bosses"} <= ids
    slot = next(s for s in cat["sections"] if s["id"] == "icons")["slots"][0]
    assert slot["prompt"] and slot["advice"]
    bad = client.post("/admin/api/web/art/upload?path=" + slot["path"], content=b"GIF89a", headers=H())
    assert bad.status_code == 400
    assert client.post("/admin/api/web/art/upload?path=../etc/passwd", content=png(4, 4), headers=H()).status_code == 400
    ok = client.post("/admin/api/web/art/upload?path=" + slot["path"], content=png(256, 256), headers=H()).json()
    assert ok["width"] == 256 and ok["height"] == 256
    assert client.get("/admin/api/web/art/file?path=" + slot["path"], headers=H()).content.startswith(b"\x89PNG")
    pub = client.post("/admin/api/web/art/publish", headers=H()).json()
    assert pub["files"] == 1 and pub["version"] >= 1
    man = client.get("/api/v1/content/manifest?channel=dev&client_version=0.6.3").json()["manifest"]
    assert any(p["package_id"] == "ui.art" for p in man["packages"])
    from app.content import service
    from app.core.db import get_db
    gen = get_db()
    db = next(gen)
    service.remove(db, "ui.art", "dev", admin="test")  # the blob lives in this test's temporary store
    db.commit()
    gen.close()


def _jpeg(w, h):
    # minimal JPEG header with an SOF0 segment (enough for size detection)
    import struct
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + \
        b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00" + b"\xff\xd9"


def test_art_catalog_groups_formats_and_jpeg(client):
    cat = client.get("/admin/api/web/art", headers=H()).json()
    ids = [s["id"] for s in cat["sections"]]
    assert {"screens", "shell", "buttons", "panels", "currency", "icons", "factions", "cards", "heroes", "bosses",
            "regions", "battle", "story", "chat", "guild", "shop"} <= set(ids)
    slots = [sl for s in cat["sections"] for sl in s["slots"]]
    assert len({sl["path"] for sl in slots}) == len(slots)  # no duplicates across groups
    for sl in slots:
        if sl.get("model"):
            assert sl["formats"] == "GLB" and "glb" in sl["prompt"].lower() and sl["where"]
            continue
        w, h = sl["size"].split("×")
        assert f"exactly {w}x{h} pixels" in sl["prompt"] and sl["where"] and sl["formats"] in ("PNG", "PNG / JPEG")
    opaque = next(sl for sl in slots if sl["path"] == "ui/app_bg.png")
    alpha = next(sl for sl in slots if sl["path"] == "ui/buttons/primary.png")
    assert not opaque["alpha"] and alpha["alpha"]
    r = client.post("/admin/api/web/art/upload?path=ui/app_bg.png", content=_jpeg(1080, 1920), headers=H())
    assert r.status_code == 200 and r.json()["format"] == "jpg" and r.json()["height"] == 1920
    assert client.get("/admin/api/web/art/file?path=ui/app_bg.png", headers=H()).headers["content-type"] == "image/jpeg"
    bad = client.post("/admin/api/web/art/upload?path=ui/buttons/primary.png", content=_jpeg(360, 120), headers=H())
    assert bad.status_code == 400 and "PNG" in bad.json()["detail"]["message"]
    client.post("/admin/api/web/art/remove?path=ui/app_bg.png", headers=H())


def test_every_art_slot_is_read_by_the_client():
    """No decorative slots: each catalog path (or its template) must appear in the Godot client sources."""
    from pathlib import Path
    from app.admin_web import art
    src = "\n".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[2] / "client" / "src").rglob("*.gd"))
    templates = {"icons/": '"icons/%s.png"', "heroes/": '"heroes/%s.png"', "guild/banner_": '"guild/banner_%s.png"',
                 "ui/chat/": '"ui/chat/"', "ui/buttons/": '"ui/buttons/%s.png"', "ui/cards/frame_r": '"ui/cards/frame_r%d.png"',
                 "regions/": '"regions/%s.png"', "ui/battle/": '"ui/battle/%s.png"',
                 "ui/shop/items/": '"ui/shop/items/%s.png"', "ui/home/shop_button": '"ui/home/shop_button.png"', "ui/story/": '"ui/story/%s.png"', "ui/shop/banner_": '"ui/shop/banner_%s.png"',
                 "caravan/modules/": '"caravan/modules/%s.png"', "models/heroes/": '"looks/%s.json"',
                 "maps/regions/": '"art/maps/regions/%s.glb"', "maps/battle/": '"art/maps/battle/%s.glb"'}
    for sec in art.catalog():
        for sl in sec["slots"]:
            tpl = next((t for pre, t in templates.items() if sl["path"].startswith(pre)), None)
            needle = tpl if tpl else '"' + sl["path"] + '"'
            assert needle in src, f"{sl['path']} is not used by the client ({needle})"


def test_glb_models_upload_settings_and_separate_package(client):
    """3D models: GLB validated, animations read, mapping + scale saved, published as ui.models3d with looks json."""
    import io
    import json as _json
    import zipfile
    from pathlib import Path
    from sqlalchemy import select
    glb = (Path(__file__).resolve().parents[2] / "client/assets/third_party/kaykit_adventurers/Knight.glb").read_bytes()
    assert client.post("/admin/api/web/art/upload?path=models/heroes/ilgiz.glb", content=b"not a model", headers=H()).status_code == 400
    r = client.post("/admin/api/web/art/upload?path=models/heroes/ilgiz.glb", content=glb, headers=H())
    assert r.status_code == 200 and r.json()["format"] == "glb" and len(r.json()["animations"]) > 5
    anims = r.json()["animations"]
    assert r.json()["anims"].get("idle")  # guessed from the names
    s = client.post("/admin/api/web/art/model-settings?path=models/heroes/ilgiz.glb", headers=H(),
                    json={"scale": 1.2, "anims": {"idle": anims[0], "attack": anims[1], "bogus": "x"}}).json()
    assert s["scale"] == 1.2 and "bogus" not in s["anims"]
    assert client.get("/admin/api/web/art/file?path=models/heroes/ilgiz.glb", headers=H()).headers["content-type"] == "model/gltf-binary"
    pub = client.post("/admin/api/web/art/publish", headers=H()).json()
    assert pub.get("models") and pub["models"]["version"] >= 1
    from app.core.db import get_db
    from app.models import ContentPackageVersion
    gen = get_db()
    db = next(gen)
    try:
        row = db.scalar(select(ContentPackageVersion).where(ContentPackageVersion.package_id == "ui.models3d")
                        .order_by(ContentPackageVersion.version.desc()))
        assert row is not None
        from app.content import service
        from app.content.store import path_for
        z = zipfile.ZipFile(io.BytesIO(path_for(row.sha256).read_bytes()))
        look = _json.loads(z.read("looks/ilgiz.json"))
        assert look["rig"] == "content:art/models/heroes/ilgiz.glb" and look["scale"] == 1.2
        assert "art/models/heroes/ilgiz.glb" in z.namelist()
        for pid in ("ui.models3d", "ui.art"):  # blobs live in this test's temporary store
            try:
                service.remove(db, pid, "dev", admin="test")
            except Exception:
                pass
    finally:
        gen.close()
    client.post("/admin/api/web/art/remove?path=models/heroes/ilgiz.glb", headers=H())
