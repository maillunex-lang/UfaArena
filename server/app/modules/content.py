"""Uralia Update System — delivery API.

Signed manifest (RSA-SHA256 over the exact `manifest_raw` bytes), content-addressed package
files with HTTP Range (resumable downloads; CDN-mirrorable), install reports.
Publishing/rollback/kill switch are done with `python -m app.content.admin` (see admin.py).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..content import pack, service, store
from ..core import signing
from ..core.db import get_db
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..game import data as D
from ..models import ContentInstallation, ContentManifestVersion

router = APIRouter(prefix="/content", tags=["content"])
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def balance_package_bytes() -> bytes:
    body = {"version": 1, "rarities": D.RARITIES, "factions": D.FACTIONS, "classes": D.CLASSES,
            "buildings": D.BUILDINGS}
    return pack.build({"package_id": "core.balance", "version": 1, "kind": "balance", "title": "Баланс и справочники",
                       "min_client_version": "0.1.0", "dependencies": [], "required": True},
                      {"data/balance.json": signing.canonical(body)})


def ensure_initial(db: Session) -> None:
    """Publish core.balance into dev on first start, or when the active manifest references blobs that
    are not in the store (e.g. upgrade from the 0.1 slice which served core.balance from code)."""
    cur = service.active(db, "dev")
    if cur is None or any(not store.exists(p.get("sha256", "")) or "/files/" not in p.get("url", "")
                          for p in cur.packages):
        service.publish(db, balance_package_bytes(), "dev", notes="initial core.balance", admin="seed")


def _semver(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


@router.get("/manifest")
def manifest(channel: str = Query(default="dev", pattern="^(dev|test|beta|stable)$"),
             platform: str = Query(default="android", max_length=16),
             client_version: str = Query(default="0.0.0", max_length=16),
             db: Session = Depends(get_db)):
    row = service.active(db, channel, platform)
    if row is None:
        raise GameError("not_found", "Манифест не найден", 404)
    body = {"channel": channel, "platform": platform, "version": row.version,
            "minimum_client_version": row.minimum_client_version, "kill_switch": row.kill_switch,
            "created_at": row.created_at.isoformat() if row.created_at else "", "notes": row.notes,
            "packages": row.packages}
    raw = signing.canonical(body)
    return {"manifest": body, "manifest_raw": raw.decode(), "signature": signing.sign(body),
            "algorithm": "RSA-PKCS1v15-SHA256",
            "client_update_required": _semver(client_version) < _semver(row.minimum_client_version)}


@router.get("/public-key")
def public_key():
    return Response(signing.public_key_pem(), media_type="application/x-pem-file")


@router.get("/files/{sha256}")
def package_file(sha256: str):
    """Immutable blob by hash. Supports `Range: bytes=a-b` (206) for resumable downloads."""
    if not SHA_RE.match(sha256) or not store.exists(sha256):
        raise GameError("not_found", "Файл не найден", 404)
    return FileResponse(store.path_for(sha256), media_type="application/zip",
                        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{sha256}"'})


class VerifyIn(BaseModel):
    manifest_version: int
    channel: str = Field(pattern="^(dev|test|beta|stable)$")
    status: str = Field(pattern="^(ok|hash_mismatch|signature_invalid|rolled_back|invalid_package|no_space|kill_switch)$")
    packages: dict[str, str] = Field(default_factory=dict)  # package_id -> sha256 seen by client
    details: dict = Field(default_factory=dict)


@router.post("/verify-install")
def verify_install(body: VerifyIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    row = db.scalar(select(ContentManifestVersion).where(ContentManifestVersion.channel == body.channel,
                                                         ContentManifestVersion.version == body.manifest_version))
    expected = {p["package_id"]: p["sha256"] for p in (row.packages if row else [])}
    mismatched = [k for k, v in body.packages.items() if expected.get(k) != v]
    status = body.status if not mismatched else "hash_mismatch"
    db.add(ContentInstallation(user_id=user.id, manifest_version=body.manifest_version, channel=body.channel,
                               status=status, details={"mismatched": mismatched, **body.details}))
    db.commit()
    return {"accepted": not mismatched and status == "ok", "status": status, "mismatched": mismatched}
