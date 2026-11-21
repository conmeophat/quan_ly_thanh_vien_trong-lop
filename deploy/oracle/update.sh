#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
if systemctl is-active --quiet class-merit-backup.service; then echo "Backup running; refusing update."; exit 1; fi
if [[ -x /usr/local/sbin/class-merit-backup && -f /etc/class-merit-hub/backup.env ]]; then
  /usr/local/sbin/class-merit-backup
else
  echo "WARNING: offsite backup is not configured."
  read -r -p "Continue without backup? Type CONTINUE: " CONFIRM
  [[ "$CONFIRM" == "CONTINUE" ]] || exit 1
fi
cd /opt/class-merit-hub
git fetch origin main
git pull --ff-only origin main
.venv/bin/pip install -r requirements.txt
chown -R classmerit:classmerit /opt/class-merit-hub
if [[ -f /etc/class-merit-hub/backup.env ]]; then
  install -m 0750 -o root -g root \
    /opt/class-merit-hub/deploy/oracle/backup.sh \
    /usr/local/sbin/class-merit-backup
  install -m 0750 -o root -g root \
    /opt/class-merit-hub/deploy/oracle/verify_backup.sh \
    /usr/local/sbin/class-merit-verify-backup
fi
systemctl restart class-merit-hub
sleep 5
curl --fail --silent http://127.0.0.1:8080/healthz
echo
echo "Update completed."
