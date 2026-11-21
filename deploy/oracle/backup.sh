#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
source /etc/class-merit-hub/backup.env
LOCK=/run/lock/class-merit-backup.lock
exec 9>"$LOCK"
flock -n 9 || { echo "A backup is already running."; exit 0; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BASENAME="class-merit-$STAMP.sqlite3.gz.age"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$LOCAL_BACKUP_DIR"
chmod 0700 "$LOCAL_BACKUP_DIR"
if [[ ! -s "$DATABASE_PATH" ]]; then echo "Database file missing or empty: $DATABASE_PATH" >&2; exit 1; fi
if [[ ! -s "$AGE_RECIPIENT_FILE" ]]; then echo "Encryption recipient is missing." >&2; exit 1; fi

echo "Creating consistent SQLite backup..."
python3 - "$DATABASE_PATH" "$WORK/database.sqlite3" <<'PY'
import sqlite3
import sys
source_path, destination_path = sys.argv[1:3]
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=60)
destination = sqlite3.connect(destination_path, timeout=60)
try:
    source.backup(destination, pages=256, sleep=0.05)
    result = destination.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"SQLite integrity check failed: {result}")
finally:
    destination.close()
    source.close()
PY

gzip -9 "$WORK/database.sqlite3"
age -r "$(cat "$AGE_RECIPIENT_FILE")" -o "$WORK/$BASENAME" "$WORK/database.sqlite3.gz"
install -m 0600 "$WORK/$BASENAME" "$LOCAL_BACKUP_DIR/$BASENAME"

echo "Uploading encrypted backup to OCI Object Storage..."
oci os object put --auth instance_principal \
  --namespace-name "$OCI_NAMESPACE" --bucket-name "$OCI_BUCKET" \
  --name "$OCI_PREFIX$BASENAME" --file "$WORK/$BASENAME" --force --output json >/dev/null

find "$LOCAL_BACKUP_DIR" -maxdepth 1 -type f -name 'class-merit-*.sqlite3.gz.age' -mtime +14 -delete
DELETE_NAMES="$(
  oci os object list --auth instance_principal --namespace-name "$OCI_NAMESPACE" \
    --bucket-name "$OCI_BUCKET" --prefix "$OCI_PREFIX" --all --output json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); names=sorted(x["name"] for x in d.get("data",[]) if x["name"].endswith(".sqlite3.gz.age")); print("\n".join(names[:-60]))'
)"
if [[ -n "$DELETE_NAMES" ]]; then
  while IFS= read -r old_name; do
    [[ -z "$old_name" ]] && continue
    oci os object delete --auth instance_principal --namespace-name "$OCI_NAMESPACE" \
      --bucket-name "$OCI_BUCKET" --object-name "$old_name" --force >/dev/null
  done <<< "$DELETE_NAMES"
fi
echo "Backup completed: $BASENAME"
