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
