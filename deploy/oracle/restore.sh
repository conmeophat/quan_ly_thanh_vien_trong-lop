#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
if (( $# != 2 )); then
  echo "Usage: sudo bash deploy/oracle/restore.sh BACKUP.sqlite3.gz.age AGE-IDENTITY.txt"
  exit 1
fi
if [[ ! -f "$1" || ! -f "$2" ]]; then
  echo "Backup or age identity file does not exist."
  exit 1
fi
ENCRYPTED="$1"
IDENTITY="$2"
source /etc/class-merit-hub/backup.env
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
chmod 0700 "$WORK"

age -d -i "$IDENTITY" -o "$WORK/backup.sqlite3.gz" "$ENCRYPTED"
gzip -t "$WORK/backup.sqlite3.gz"
gzip -dc "$WORK/backup.sqlite3.gz" > "$WORK/restored.sqlite3"
python3 - "$WORK/restored.sqlite3" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
try:
    check = db.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok":
        raise SystemExit(f"Integrity check failed: {check}")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {"users", "scores", "evaluations", "login_throttle", "audit_logs"}
    if not required.issubset(tables):
        raise SystemExit("Not a complete Class Merit Hub database.")
finally:
    db.close()
PY

echo "Restore file passed validation."
read -r -p "This replaces the live database. Type RESTORE to continue: " CONFIRM
if [[ "$CONFIRM" != "RESTORE" ]]; then echo "Cancelled."; exit 1; fi
systemctl stop class-merit-hub
mkdir -p "$(dirname "$DATABASE_PATH")"
if [[ -f "$DATABASE_PATH" ]]; then cp -a "$DATABASE_PATH" "$DATABASE_PATH.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"; fi
install -o classmerit -g classmerit -m 0640 "$WORK/restored.sqlite3" "$DATABASE_PATH"
rm -f "$DATABASE_PATH-wal" "$DATABASE_PATH-shm"
systemctl start class-merit-hub
sleep 5
if ! curl --fail --silent http://127.0.0.1:8080/healthz >/dev/null; then
  echo "Health check failed after restore. Inspect journalctl -u class-merit-hub."
  exit 1
fi
echo "Restore completed and app health check passed."
