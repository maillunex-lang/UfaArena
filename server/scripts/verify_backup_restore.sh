#!/usr/bin/env bash
# Backup -> restore into a scratch DB -> compare row counts of key tables and wallet/ledger reconciliation.
# Usage: PGHOST=.. PGPORT=.. PGUSER=.. SRC_DB=uralia ./verify_backup_restore.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
SCRATCH="uralia_restore_check_$$"
DATABASE_URL="postgresql:///$SRC_DB" "$DIR/backup.sh" "$TMP" > "$TMP/name"
createdb "$SCRATCH"
trap 'dropdb --if-exists "$SCRATCH"; rm -rf "$TMP"' EXIT
DATABASE_URL="postgresql:///$SCRATCH" "$DIR/restore.sh" "$(cat "$TMP/name")"
Q="select (select count(*) from users), (select count(*) from player_heroes), (select count(*) from wallet_transactions),
   (select count(*) from player_campaign_progress), (select coalesce(sum(balance),0) from wallets),
   (select count(*) from (select w.user_id, w.currency from wallets w left join (select user_id, currency, sum(delta) s
     from wallet_transactions group by 1,2) l using (user_id, currency) where w.balance <> coalesce(l.s,0)) bad)"
A="$(psql -tA -d "$SRC_DB" -c "$Q")"
B="$(psql -tA -d "$SCRATCH" -c "$Q")"
echo "source:   $A"
echo "restored: $B"
[ "$A" = "$B" ] || { echo "MISMATCH"; exit 1; }
[ "${A##*|}" = "0" ] || { echo "LEDGER NOT RECONCILED"; exit 1; }
echo "BACKUP_RESTORE_OK"
