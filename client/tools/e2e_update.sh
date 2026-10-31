#!/usr/bin/env bash
# Orchestrates tools/E2EUpdate.gd: runs a fresh server + the client, performs server-side
# release actions when the client asks. Usage: tools/e2e_update.sh <godot> <workdir>
set -euo pipefail
GODOT="$1"; W="$2"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
rm -rf "$W"; mkdir -p "$W"
export URALIA_DATABASE_URL="sqlite:///$W/e2e.db" URALIA_CONTENT_SIGNING_KEY_PATH="$W/sign.pem" URALIA_CONTENT_STORE_PATH="$W/store"
cd "$ROOT/server"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$W/server.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
for i in $(seq 1 40); do curl -sf 127.0.0.1:8000/health/ready >/dev/null && break; sleep 0.5; done
ADMIN=".venv/bin/python -m app.content.admin"
SRC="$ROOT/content_src/fortress_autumn_fair"
wait_ready() { while [ ! -f "$W/step_$1.ready" ]; do sleep 0.3; done; }
done_() { touch "$W/step_$1.done"; }
(
  wait_ready 1; $ADMIN publish "$SRC" --notes "autumn fair" ; done_ 1
  wait_ready 2; PREV=$($ADMIN list | sed -n 2p | grep -o 'v[0-9]*' | head -1 | tr -d v); $ADMIN activate "$PREV"; done_ 2
  wait_ready 3
  cp -r "$SRC" "$W/v2"; sed -i 's/"version": 1/"version": 2/' "$W/v2/package.json"
  head -c 400000 /dev/urandom > "$W/v2/notes.txt"   # make the archive > 1 chunk
  $ADMIN publish "$W/v2" --notes "autumn fair v2"; done_ 3
  wait_ready 4
  cp -r "$W/v2" "$W/v3"; sed -i 's/"version": 2/"version": 3/' "$W/v3/package.json"
  $ADMIN publish "$W/v3" --notes "v3 (will be corrupted)"
  BLOB=$(find "$W/store" -type f -newer "$W/step_4.ready" | head -1)
  SZ=$(stat -c %s "$BLOB"); head -c "$SZ" /dev/urandom > "$BLOB"; done_ 4
  wait_ready 5; $ADMIN kill on; done_ 5
  wait_ready 6; $ADMIN kill off; V2=$($ADMIN list | grep 'autumn fair v2' | grep -o 'v[0-9]*' | head -1 | tr -d v); $ADMIN activate "$V2"; done_ 6
) > "$W/admin.log" 2>&1 &
cd "$ROOT/client"
rm -rf ~/.local/share/godot/app_userdata/*
URALIA_E2E_UPDATE="$W" timeout 600 xvfb-run -a -s "-screen 0 1080x1920x24" "$GODOT" --path . --resolution 540x960 2>&1 | grep -E "UPD:|SCRIPT ERROR" || true
echo "--- admin.log"; cat "$W/admin.log"
