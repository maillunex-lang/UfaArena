#!/usr/bin/env bash
# Usage: DATABASE_URL=postgresql://user@host:port/db ./backup.sh [out_dir]
# Custom-format pg_dump (compressed, restorable selectively), with SHA-256 sidecar.
set -euo pipefail
OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT_DIR/uralia_${TS}.dump"
pg_dump --format=custom --no-owner --no-privileges --dbname="${DATABASE_URL}" --file="$FILE"
sha256sum "$FILE" > "$FILE.sha256"
echo "$FILE"
