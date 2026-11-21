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
CONFIG=/etc/class-merit-hub/backup.env
APP_ENV=/etc/class-merit-hub/app.env
DATABASE_PATH=""

# A disaster-recovery VM may not have backup.env yet. The application database
# path is sufficient for a one-time restore; backup upload can be configured later.
if [[ -f "$CONFIG" ]]; then
  source "$CONFIG"
elif [[ -f "$APP_ENV" ]]; then
  DATABASE_PATH="$(grep '^DATABASE_PATH=' "$APP_ENV" | tail -n 1 | cut -d= -f2-)"
else
  echo "Neither backup.env nor app.env exists; install the application first." >&2
  exit 1
fi
if [[ -z "$DATABASE_PATH" ]]; then
  echo "DATABASE_PATH is missing from the application configuration." >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
chmod 0700 "$WORK"

if [[ -f "$ENCRYPTED.sha256" ]]; then
  EXPECTED_SHA="$(tr -d '[:space:]' < "$ENCRYPTED.sha256")"
  ACTUAL_SHA="$(sha256sum "$ENCRYPTED" | awk '{print $1}')"
  if [[ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]]; then
    echo "SHA-256 mismatch; refusing to restore a damaged or altered backup." >&2
    exit 1
  fi
  echo "SHA-256 checksum: OK"
else
  echo "No sidecar checksum supplied; continuing with decryption and database integrity checks."
fi

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

echo "Restore file passed decryption, gzip, SQLite and schema validation."
read -r -p "This replaces the live database at $DATABASE_PATH. Type RESTORE to continue: " CONFIRM
if [[ "$CONFIRM" != "RESTORE" ]]; then echo "Cancelled."; exit 1; fi
mkdir -p "$(dirname "$DATABASE_PATH")"
PREVIOUS_DATABASE=""
if [[ -f "$DATABASE_PATH" ]]; then
  PREVIOUS_DATABASE="$DATABASE_PATH.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"
  # Use SQLite's online backup API so the snapshot includes committed WAL data.
  python3 - "$DATABASE_PATH" "$PREVIOUS_DATABASE" <<'PY'
import sqlite3
import sys

source_path, destination_path = sys.argv[1:3]
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=60)
destination = sqlite3.connect(destination_path, timeout=60)
try:
    source.backup(destination, pages=256, sleep=0.05)
    result = destination.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"Pre-restore SQLite snapshot failed integrity_check: {result}")
finally:
    destination.close()
    source.close()
PY
  chown classmerit:classmerit "$PREVIOUS_DATABASE"
  chmod 0640 "$PREVIOUS_DATABASE"
fi

systemctl stop class-merit-hub
install -o classmerit -g classmerit -m 0640 "$WORK/restored.sqlite3" "$DATABASE_PATH"
rm -f "$DATABASE_PATH-wal" "$DATABASE_PATH-shm"
systemctl start class-merit-hub
sleep 5
if ! curl --fail --silent http://127.0.0.1:8080/healthz >/dev/null; then
  echo "Health check failed after restore."
  if [[ -n "$PREVIOUS_DATABASE" && -f "$PREVIOUS_DATABASE" ]]; then
    echo "Rolling back to the pre-restore database..."
    systemctl stop class-merit-hub || true
    install -o classmerit -g classmerit -m 0640 "$PREVIOUS_DATABASE" "$DATABASE_PATH"
    rm -f "$DATABASE_PATH-wal" "$DATABASE_PATH-shm"
    systemctl start class-merit-hub
  else
    echo "No previous database existed to roll back to."
  fi
  echo "Inspect journalctl -u class-merit-hub for the cause."
  exit 1
fi
echo "Restore completed and app health check passed."
if [[ -n "$PREVIOUS_DATABASE" ]]; then
  echo "Pre-restore database retained at: $PREVIOUS_DATABASE"
fi
