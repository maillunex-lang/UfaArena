"""Content-addressed blob store on disk (a CDN/object storage can mirror it 1:1 by SHA-256)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..core.config import get_settings


def root() -> Path:
    p = Path(get_settings().content_store_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def path_for(sha256: str) -> Path:
    return root() / sha256[:2] / sha256


def put(data: bytes) -> str:
    sha = hashlib.sha256(data).hexdigest()
    dest = path_for(sha)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)  # atomic
    return sha


def exists(sha256: str) -> bool:
    return path_for(sha256).exists()
