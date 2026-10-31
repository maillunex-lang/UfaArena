"""Content package format and validation (data only — never executable code).

A package is a ZIP archive:
    package.json   {"package_id", "version", "kind", "title", "min_client_version",
                    "dependencies": [ids], "required": bool}
    <assets>       only whitelisted data types (glTF binary, images, Ogg audio, JSON, text)

Clients load these with runtime importers (GLTFDocument, Image, AudioStreamOggVorbis, JSON),
so a package cannot carry scripts, scenes, native libraries or Godot resource packs.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass

ALLOWED_EXT = {".json", ".glb", ".png", ".jpg", ".jpeg", ".webp", ".ogg", ".txt", ".md"}
MAX_PACKAGE_BYTES = 200 * 1024 * 1024
MAX_ENTRIES = 4000
MAX_UNCOMPRESSED = 600 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,62}$")
VER_RE = re.compile(r"^\d+\.\d+\.\d+$")
KINDS = {"heroes", "textures", "animations", "audio", "ui", "l10n", "maps", "chapters", "events", "balance",
         "assets", "fortress"}


class PackageError(ValueError):
    pass


@dataclass
class PackageInfo:
    package_id: str
    version: int
    kind: str
    title: str
    min_client_version: str
    dependencies: list[str]
    required: bool
    files: list[str]


def validate(data: bytes) -> PackageInfo:
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError("package too large")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise PackageError(f"not a zip archive: {e}") from e
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise PackageError("too many files")
    total = 0
    files: list[str] = []
    for i in infos:
        name = i.filename
        if i.is_dir():
            continue
        if name.startswith("/") or "\\" in name or ".." in name.split("/") or ":" in name:
            raise PackageError(f"unsafe path: {name}")
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext not in ALLOWED_EXT:
            raise PackageError(f"file type not allowed: {name}")
        total += i.file_size
        if total > MAX_UNCOMPRESSED:
            raise PackageError("uncompressed size too large")
        files.append(name)
    if "package.json" not in files:
        raise PackageError("package.json missing")
    try:
        meta = json.loads(zf.read("package.json"))
    except Exception as e:
        raise PackageError(f"package.json invalid: {e}") from e
    for name in files:
        if name.endswith(".json") and name != "package.json":
            try:
                json.loads(zf.read(name))
            except Exception as e:
                raise PackageError(f"invalid JSON in {name}: {e}") from e
        if name.endswith(".glb") and zf.read(name)[:4] != b"glTF":
            raise PackageError(f"not a binary glTF: {name}")
    pid = str(meta.get("package_id", ""))
    if not ID_RE.match(pid):
        raise PackageError("bad package_id")
    version = meta.get("version")
    if not isinstance(version, int) or version < 1:
        raise PackageError("version must be a positive integer")
    kind = meta.get("kind", "assets")
    if kind not in KINDS:
        raise PackageError(f"unknown kind {kind}")
    mcv = str(meta.get("min_client_version", "0.1.0"))
    if not VER_RE.match(mcv):
        raise PackageError("bad min_client_version")
    deps = meta.get("dependencies", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) and ID_RE.match(d) for d in deps) or pid in deps:
        raise PackageError("bad dependencies")
    return PackageInfo(pid, version, kind, str(meta.get("title", pid))[:120], mcv, deps,
                       bool(meta.get("required", False)), sorted(files))


def build(meta: dict, files: dict[str, bytes]) -> bytes:
    """Deterministic zip (fixed timestamps, sorted entries) so identical content => identical SHA-256."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entries = {"package.json": json.dumps(meta, ensure_ascii=False, sort_keys=True, indent=1).encode(), **files}
        for name in sorted(entries):
            zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED if name.endswith((".ogg", ".png", ".jpg", ".webp")) else zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, entries[name])
    return buf.getvalue()
