#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

CONFIG=/etc/class-merit-hub/backup.env
[[ -f "$CONFIG" ]] || { echo "Missing $CONFIG; configure backups first." >&2; exit 1; }
source "$CONFIG"

if (( $# > 2 )); then
  echo "Usage: sudo bash deploy/oracle/verify_backup.sh [BACKUP.sqlite3.gz.age] [AGE-IDENTITY.txt]" >&2
  exit 1
fi

BACKUP=""
IDENTITY=/root/class-merit-backup-identity.txt
if (( $# >= 1 )); then BACKUP="$1"; fi
if (( $# == 2 )); then IDENTITY="$2"; fi
if [[ -z "$BACKUP" ]]; then
  BACKUP="$(find "$LOCAL_BACKUP_DIR" -maxdepth 1 -type f -name 'class-merit-*.sqlite3.gz.age' -printf '%f\n' | sort | tail -n 1)"
  [[ -n "$BACKUP" ]] && BACKUP="$LOCAL_BACKUP_DIR/$BACKUP"
fi
[[ -s "$BACKUP" ]] || { echo "Backup file missing or empty: $BACKUP" >&2; exit 1; }
[[ -s "$IDENTITY" ]] || { echo "Age identity file missing: $IDENTITY" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
chmod 0700 "$WORK"

EXPECTED_SHA="$(sha256sum "$BACKUP" | awk '{print $1}')"
if [[ -f "$BACKUP.sha256" ]]; then
  STORED_SHA="$(tr -d '[:space:]' < "$BACKUP.sha256")"
  [[ "$EXPECTED_SHA" == "$STORED_SHA" ]] || {
    echo "SHA-256 checksum mismatch. The backup may be damaged." >&2
    exit 1
  }
  echo "SHA-256 checksum: OK"
else
  echo "No sidecar checksum found (older backup format); continuing with decryption and database checks."
fi

age -d -i "$IDENTITY" -o "$WORK/backup.sqlite3.gz" "$BACKUP"
gzip -t "$WORK/backup.sqlite3.gz"
gzip -dc "$WORK/backup.sqlite3.gz" > "$WORK/verified.sqlite3"

python3 - "$WORK/verified.sqlite3" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60)
try:
    result = db.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"SQLite integrity_check failed: {result}")
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"users", "scores", "evaluations", "login_throttle", "audit_logs"}
    missing = required - tables
    if missing:
        raise SystemExit(
            "Backup is not a complete Class Merit Hub database; missing: "
            + ", ".join(sorted(missing))
        )
finally:
    db.close()
print("SQLite integrity_check: ok")
print("Required Class Merit Hub tables: present")
PY

echo "BACKUP VERIFIED — no live database was changed."
echo "File: $BACKUP"
echo "SHA-256: $EXPECTED_SHA"
