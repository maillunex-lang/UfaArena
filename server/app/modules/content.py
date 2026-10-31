"""Uralia Update System — server side, first slice.

Signed manifest (RSA-SHA256 over canonical JSON) with package id, version, platform,
minimum client version, dependencies, size, SHA-256 and URL. Content packages are
pure data (JSON / Godot resource packs without scripts) and never executable code.
Channels dev/test/beta/stable, kill switch and rollback = re-activating an older
manifest version. Admin publishing tooling is a later block.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import signing
from ..core.db import get_db
from ..core.deps import CurrentUser, player
from ..core.errors import GameError
from ..game import data as D
from ..models import ContentInstallation, ContentManifestVersion

router = APIRouter(prefix="/content", tags=["content"])
BALANCE_VERSION = 1


def balance_payload() -> bytes:
    body = {"version": BALANCE_VERSION, "rarities": D.RARITIES, "factions": D.FACTIONS, "classes": D.CLASSES,
            "buildings": D.BUILDINGS}
    return signing.canonical(body)


def build_balance_package() -> dict:
    raw = balance_payload()
    return {"package_id": "core.balance", "version": BALANCE_VERSION, "kind": "balance", "platform": "any",
            "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "dependencies": [],
            "url": f"/api/v1/content/packages/core.balance/{BALANCE_VERSION}"}


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
    row = db.scalar(select(ContentManifestVersion)
                    .where(ContentManifestVersion.channel == channel, ContentManifestVersion.platform == platform,
                           ContentManifestVersion.is_active.is_(True))
                    .order_by(ContentManifestVersion.version.desc()))
    if row is None:
        raise GameError("not_found", "Манифест не найден", 404)
    body = {"channel": channel, "platform": platform, "version": row.version,
            "minimum_client_version": row.minimum_client_version, "kill_switch": row.kill_switch,
            "packages": row.packages}
    return {"manifest": body, "signature": signing.sign(body), "algorithm": "RSA-PKCS1v15-SHA256",
            "client_update_required": _semver(client_version) < _semver(row.minimum_client_version)}


@router.get("/public-key")
def public_key():
    return Response(signing.public_key_pem(), media_type="application/x-pem-file")


@router.get("/packages/core.balance/{version}")
def balance_package(version: int):
    if version != BALANCE_VERSION:
        raise GameError("not_found", "Версия пакета не найдена", 404)
    return Response(balance_payload(), media_type="application/json")


class VerifyIn(BaseModel):
    manifest_version: int
    channel: str = Field(pattern="^(dev|test|beta|stable)$")
    status: str = Field(pattern="^(ok|hash_mismatch|signature_invalid|rolled_back)$")
    packages: dict[str, str] = Field(default_factory=dict)  # package_id -> sha256 seen by client


@router.post("/verify-install")
def verify_install(body: VerifyIn, user: CurrentUser = Depends(player), db: Session = Depends(get_db)):
    row = db.scalar(select(ContentManifestVersion).where(ContentManifestVersion.channel == body.channel,
                                                         ContentManifestVersion.version == body.manifest_version))
    expected = {p["package_id"]: p["sha256"] for p in (row.packages if row else [])}
    mismatched = [k for k, v in body.packages.items() if expected.get(k) != v]
    status = body.status if not mismatched else "hash_mismatch"
    db.add(ContentInstallation(user_id=user.id, manifest_version=body.manifest_version, channel=body.channel,
                               status=status, details={"mismatched": mismatched}))
    db.commit()
    return {"accepted": not mismatched and status == "ok", "status": status, "mismatched": mismatched}
