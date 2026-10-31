"""Release management for the Uralia Update System.

Every change creates a NEW immutable manifest version and activates it; rollback is just
activating an older version. Exactly one active manifest per (channel, platform).
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import AdminAction, ContentManifestVersion, ContentPackage, ContentPackageVersion
from . import pack, store

CHANNELS = ("dev", "test", "beta", "stable")
PLATFORMS = ("android",)


class ReleaseError(ValueError):
    pass


def _check_channel(channel: str) -> None:
    if channel not in CHANNELS:
        raise ReleaseError(f"unknown channel {channel}")


def active(db: Session, channel: str, platform: str = "android") -> ContentManifestVersion | None:
    return db.scalar(select(ContentManifestVersion).where(
        ContentManifestVersion.channel == channel, ContentManifestVersion.platform == platform,
        ContentManifestVersion.is_active.is_(True)))


def file_url(sha256: str) -> str:
    base = get_settings().content_base_url
    return f"{base.rstrip('/')}/{sha256}" if base else f"/api/v1/content/files/{sha256}"


def _entry(pv: ContentPackageVersion) -> dict:
    return {"package_id": pv.package_id, "version": pv.version, "kind": pv.kind, "title": pv.title,
            "size": pv.size, "sha256": pv.sha256, "url": file_url(pv.sha256), "dependencies": pv.dependencies,
            "required": pv.required, "min_client_version": pv.min_client_version, "platform": "any"}


def _validate_graph(packages: list[dict]) -> list[dict]:
    """Dependencies must exist in the manifest; returns packages in dependency order."""
    by_id = {p["package_id"]: p for p in packages}
    for p in packages:
        for d in p["dependencies"]:
            if d not in by_id:
                raise ReleaseError(f"{p['package_id']} depends on missing package {d}")
    ordered, state = [], {}

    def visit(pid: str) -> None:
        if state.get(pid) == 1:
            raise ReleaseError(f"dependency cycle at {pid}")
        if state.get(pid) == 2:
            return
        state[pid] = 1
        for d in by_id[pid]["dependencies"]:
            visit(d)
        state[pid] = 2
        ordered.append(by_id[pid])

    for pid in sorted(by_id):
        visit(pid)
    return ordered


def _new_manifest(db: Session, channel: str, platform: str, packages: list[dict], notes: str,
                  min_client: str | None = None, admin: str = "cli") -> ContentManifestVersion:
    packages = _validate_graph(packages)
    cur = active(db, channel, platform)
    nxt = (db.scalar(select(func.max(ContentManifestVersion.version)).where(
        ContentManifestVersion.channel == channel, ContentManifestVersion.platform == platform)) or 0) + 1
    # Manifest minimum changes only explicitly (forces an APK update). Packages carry their own
    # min_client_version; older clients simply skip packages they cannot use.
    mcv = min_client or (cur.minimum_client_version if cur else "0.1.0")
    db.execute(update(ContentManifestVersion).where(ContentManifestVersion.channel == channel,
                                                    ContentManifestVersion.platform == platform)
               .values(is_active=False))
    m = ContentManifestVersion(channel=channel, platform=platform, version=nxt, minimum_client_version=mcv,
                               packages=packages, is_active=True, kill_switch=False, notes=notes)
    db.add(m)
    db.add(AdminAction(admin=admin, action="content.manifest_created",
                       details={"channel": channel, "version": nxt, "notes": notes,
                                "packages": {p["package_id"]: p["version"] for p in packages}}))
    db.flush()
    return m


def upload(db: Session, data: bytes) -> ContentPackageVersion:
    info = pack.validate(data)
    existing = db.scalar(select(ContentPackageVersion).where(ContentPackageVersion.package_id == info.package_id,
                                                             ContentPackageVersion.version == info.version))
    sha = store.put(data)
    if existing:
        if existing.sha256 != sha:
            raise ReleaseError(f"{info.package_id} v{info.version} already published with different content; "
                               f"bump the version")
        return existing
    if db.get(ContentPackage, info.package_id) is None:
        db.add(ContentPackage(package_id=info.package_id, kind=info.kind, description=info.title))
        db.flush()
    pv = ContentPackageVersion(package_id=info.package_id, version=info.version, sha256=sha, size=len(data),
                               kind=info.kind, title=info.title, min_client_version=info.min_client_version,
                               dependencies=info.dependencies, required=info.required, files=info.files)
    db.add(pv)
    db.flush()
    return pv


def publish(db: Session, data: bytes, channel: str = "dev", platform: str = "android", notes: str = "",
            admin: str = "cli") -> ContentManifestVersion:
    _check_channel(channel)
    pv = upload(db, data)
    cur = active(db, channel, platform)
    pkgs = [p for p in (cur.packages if cur else []) if p["package_id"] != pv.package_id]
    pkgs.append(_entry(pv))
    m = _new_manifest(db, channel, platform, pkgs, notes or f"publish {pv.package_id} v{pv.version}", admin=admin)
    db.commit()
    return m


def remove(db: Session, package_id: str, channel: str, platform: str = "android", admin: str = "cli"):
    cur = active(db, channel, platform)
    if cur is None or not any(p["package_id"] == package_id for p in cur.packages):
        raise ReleaseError(f"{package_id} is not in the active {channel} manifest")
    m = _new_manifest(db, channel, platform, [p for p in cur.packages if p["package_id"] != package_id],
                      f"remove {package_id}", admin=admin)
    db.commit()
    return m


def activate(db: Session, channel: str, version: int, platform: str = "android", admin: str = "cli"):
    """Rollback / roll-forward to an existing manifest version."""
    target = db.scalar(select(ContentManifestVersion).where(ContentManifestVersion.channel == channel,
                                                            ContentManifestVersion.platform == platform,
                                                            ContentManifestVersion.version == version))
    if target is None:
        raise ReleaseError(f"manifest {channel} v{version} not found")
    for p in target.packages:
        if not store.exists(p["sha256"]):
            raise ReleaseError(f"blob for {p['package_id']} is missing from the store")
    db.execute(update(ContentManifestVersion).where(ContentManifestVersion.channel == channel,
                                                    ContentManifestVersion.platform == platform)
               .values(is_active=False))
    target.is_active = True
    db.add(AdminAction(admin=admin, action="content.activate", details={"channel": channel, "version": version}))
    db.commit()
    return target


def kill_switch(db: Session, channel: str, on: bool, platform: str = "android", admin: str = "cli"):
    cur = active(db, channel, platform)
    if cur is None:
        raise ReleaseError("no active manifest")
    cur.kill_switch = on
    db.add(AdminAction(admin=admin, action="content.kill_switch", details={"channel": channel, "on": on}))
    db.commit()
    return cur


def promote(db: Session, src: str, dst: str, platform: str = "android", admin: str = "cli"):
    _check_channel(src)
    _check_channel(dst)
    cur = active(db, src, platform)
    if cur is None:
        raise ReleaseError(f"no active manifest in {src}")
    m = _new_manifest(db, dst, platform, [dict(p) for p in cur.packages], f"promote {src} v{cur.version}",
                      min_client=cur.minimum_client_version, admin=admin)
    db.commit()
    return m


def set_min_client(db: Session, channel: str, version: str, platform: str = "android", admin: str = "cli"):
    cur = active(db, channel, platform)
    if cur is None:
        raise ReleaseError("no active manifest")
    m = _new_manifest(db, channel, platform, [dict(p) for p in cur.packages], f"min client {version}",
                      min_client=version, admin=admin)
    db.commit()
    return m


def history(db: Session, channel: str, platform: str = "android", limit: int = 20) -> list[ContentManifestVersion]:
    return list(db.scalars(select(ContentManifestVersion).where(
        ContentManifestVersion.channel == channel, ContentManifestVersion.platform == platform)
        .order_by(ContentManifestVersion.version.desc()).limit(limit)))
