"""Uralia Update System: publishing, validation, signed manifest, ranged downloads, rollback, kill switch."""
import hashlib
import io
import json
import zipfile

import pytest
from sqlalchemy.orm import Session

from app.content import pack, service
from app.core import signing
from app.core.db import get_engine

import uuid

RUN = "t" + uuid.uuid4().hex[:6]
GLB = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 64


def make(pid=RUN + ".decor", version=1, files=None, **meta):
    m = {"package_id": pid, "version": version, "kind": "fortress", "title": "t", "dependencies": [], **meta}
    return pack.build(m, files if files is not None else {"fortress/decor.json": b"[]", "models/a.glb": GLB})


def manifest(client, ch="dev"):
    return client.get(f"/api/v1/content/manifest?channel={ch}&client_version=0.2.0").json()


def test_validation_rejects_code_and_unsafe_paths():
    with pytest.raises(pack.PackageError, match="not allowed"):
        pack.validate(make(files={"evil.gd": b"extends Node"}))
    with pytest.raises(pack.PackageError, match="not allowed"):
        pack.validate(make(files={"scene.tscn": b"[gd_scene]"}))
    with pytest.raises(pack.PackageError, match="not allowed"):
        pack.validate(make(files={"lib.so": b"\x7fELF"}))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("package.json", json.dumps({"package_id": "x.y", "version": 1}))
        zf.writestr("../escape.json", "{}")
    with pytest.raises(pack.PackageError, match="unsafe"):
        pack.validate(buf.getvalue())
    with pytest.raises(pack.PackageError, match="binary glTF"):
        pack.validate(make(files={"models/fake.glb": b"MZ not a gltf"}))
    with pytest.raises(pack.PackageError, match="invalid JSON"):
        pack.validate(make(files={"data/x.json": b"{nope"}))
    assert pack.validate(make()).package_id == RUN + ".decor"


def test_build_is_deterministic():
    assert make() == make()


def test_publish_rollback_kill_switch_flow(client):
    with Session(get_engine()) as db:
        base = service.active(db, "dev").version
        v1 = service.publish(db, make(version=1), "dev").version
        assert v1 == base + 1
        # same id+version with different bytes must be rejected
        with pytest.raises(service.ReleaseError, match="bump the version"):
            service.publish(db, make(version=1, files={"fortress/decor.json": b"[1]"}), "dev")
        v2 = service.publish(db, make(version=2, files={"fortress/decor.json": b"[2]"}), "dev").version
    d = manifest(client)
    assert d["manifest"]["version"] == v2
    assert signing.verify(d["manifest"], d["signature"])
    assert d["manifest_raw"].encode() == signing.canonical(d["manifest"])
    entry = next(p for p in d["manifest"]["packages"] if p["package_id"] == RUN + ".decor")
    assert entry["version"] == 2
    # full download matches hash/size
    raw = client.get(entry["url"]).content
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"]
    # resumable: ranged requests reassemble the same bytes
    half = entry["size"] // 2
    r1 = client.get(entry["url"], headers={"Range": f"bytes=0-{half - 1}"})
    r2 = client.get(entry["url"], headers={"Range": f"bytes={half}-"})
    assert r1.status_code == 206 and r2.status_code == 206
    assert r1.content + r2.content == raw
    assert "immutable" in r1.headers["cache-control"]
    # rollback to v1 manifest
    with Session(get_engine()) as db:
        service.activate(db, "dev", v1)
    entry = next(p for p in manifest(client)["manifest"]["packages"] if p["package_id"] == RUN + ".decor")
    assert entry["version"] == 1
    # kill switch is signed into the manifest
    with Session(get_engine()) as db:
        service.kill_switch(db, "dev", True)
    d = manifest(client)
    assert d["manifest"]["kill_switch"] is True and signing.verify(d["manifest"], d["signature"])
    with Session(get_engine()) as db:
        service.kill_switch(db, "dev", False)
        service.activate(db, "dev", v2)


def test_dependencies_and_promote(client):
    with Session(get_engine()) as db:
        with pytest.raises(service.ReleaseError, match="missing package"):
            service.publish(db, make(RUN + ".needs", 1, dependencies=[RUN + ".absent"]), "dev")
        db.rollback()
        service.publish(db, make(RUN + ".needs", 1, dependencies=["core.balance"]), "dev")
        service.promote(db, "dev", "beta")
    d = manifest(client, "beta")
    ids = [p["package_id"] for p in d["manifest"]["packages"]]
    assert ids.index("core.balance") < ids.index(RUN + ".needs")  # dependency order


def test_min_client_version(client):
    with Session(get_engine()) as db:
        if service.active(db, "test"):
            service.set_min_client(db, "test", "0.1.0")  # independent of previous runs on a persistent DB
        service.publish(db, make(RUN + ".future", 1, min_client_version="9.0.0"), "test")
    d = client.get("/api/v1/content/manifest?channel=test&client_version=0.2.0").json()
    # a package for newer clients must not force older clients to update the APK
    assert d["client_update_required"] is False
    entry = next(p for p in d["manifest"]["packages"] if p["package_id"] == RUN + ".future")
    assert entry["min_client_version"] == "9.0.0"
    with Session(get_engine()) as db:
        service.set_min_client(db, "test", "0.3.0")
    d = client.get("/api/v1/content/manifest?channel=test&client_version=0.2.0").json()
    assert d["client_update_required"] is True and d["manifest"]["minimum_client_version"] == "0.3.0"


def test_files_endpoint_rejects_bad_hash(client):
    assert client.get("/api/v1/content/files/../../etc/passwd").status_code == 404
    assert client.get("/api/v1/content/files/" + "0" * 64).status_code == 404


def test_cli_build_and_publish(tmp_path, client):
    from app.content import admin
    src = tmp_path / "pkg"
    (src / "fortress").mkdir(parents=True)
    (src / "package.json").write_text(json.dumps({"package_id": RUN + ".cli", "version": 1, "kind": "fortress"}))
    (src / "fortress" / "decor.json").write_text("[]")
    out = tmp_path / "p.zip"
    assert admin.main(["build", str(src), str(out)]) == 0
    assert admin.main(["publish", str(out), "--channel", "dev"]) == 0
    assert any(p["package_id"] == RUN + ".cli" for p in manifest(client)["manifest"]["packages"])
    (src / "hack.gd").write_text("extends Node")
    assert admin.main(["publish", str(src), "--channel", "dev"]) == 1
