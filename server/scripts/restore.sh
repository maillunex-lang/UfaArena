#!/usr/bin/env bash
# Usage: DATABASE_URL=postgresql://user@host:port/empty_db ./restore.sh backup.dump
set -euo pipefail
FILE="$1"
sha256sum --check "$FILE.sha256"
pg_restore --no-owner --no-privileges --exit-on-error --dbname="${DATABASE_URL}" "$FILE"
echo "restored $FILE"
