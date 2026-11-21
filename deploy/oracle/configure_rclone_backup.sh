#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
CONFIG=/etc/class-merit-hub/backup.env
[[ -f "$CONFIG" ]] || { echo "Configure OCI backup first: deploy/oracle/configure_backup.sh" >&2; exit 1; }

if ! command -v rclone >/dev/null 2>&1; then
  echo "Installing rclone from the Ubuntu package repository..."
  apt-get update
  apt-get install -y rclone
fi

echo
echo "First configure an rclone remote for a SEPARATE provider/account."
echo "Do not choose another bucket in the same OCI tenancy as your only off-site copy."
echo "Run 'rclone config' in this terminal if you have not configured a remote yet."
echo "Provider OAuth/API credentials must be entered here, never pasted into chat or GitHub."
read -r -p "Press Enter after rclone config is complete (or Ctrl+C to stop). "

read -r -p "Remote path (example: gdrive:ClassMeritHub): " REMOTE
if [[ ! "$REMOTE" =~ ^[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+$ ]]; then
  echo "Invalid remote path. Use a configured rclone remote and a path without spaces." >&2
  exit 1
fi

echo "Checking access and creating the destination folder..."
rclone mkdir "$REMOTE"

TEST_NAME=".class-merit-hub-write-test-$$"
TEST_FILE="$(mktemp)"
trap 'rm -f "$TEST_FILE"; rclone deletefile "$REMOTE/$TEST_NAME" >/dev/null 2>&1 || true' EXIT
printf 'class-merit-hub-rclone-test\n' > "$TEST_FILE"
rclone copyto "$TEST_FILE" "$REMOTE/$TEST_NAME"
REMOTE_TEST="$(rclone cat "$REMOTE/$TEST_NAME")"
[[ "$REMOTE_TEST" == "class-merit-hub-rclone-test" ]] || {
  echo "Remote write/read verification failed." >&2
  exit 1
}
rclone deletefile "$REMOTE/$TEST_NAME"
trap - EXIT
rm -f "$TEST_FILE"

python3 - "$CONFIG" "$REMOTE" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
remote = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
lines = [line for line in lines if not line.startswith("RCLONE_REMOTE=")]
lines.append(f"RCLONE_REMOTE={remote}")
temporary = path.with_suffix(".env.new")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY

install -m 0750 -o root -g root \
  /opt/class-merit-hub/deploy/oracle/backup.sh \
  /usr/local/sbin/class-merit-backup

echo
echo "Independent backup destination configured: $REMOTE"
echo "Run a backup now: sudo systemctl start class-merit-backup.service"
echo "Then verify the latest backup with verify_backup.sh."
echo "The rclone configuration may contain OAuth tokens; keep it root-only and never commit it."
