#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
if [[ ! -f /etc/class-merit-hub/app.env ]]; then echo "Install the app first."; exit 1; fi
cd /opt/class-merit-hub

echo "Installing OCI CLI into isolated Python virtual environment..."
if [[ ! -x /opt/oci-cli/bin/oci ]]; then
  python3 -m venv /opt/oci-cli
  /opt/oci-cli/bin/pip install --upgrade pip
  /opt/oci-cli/bin/pip install oci-cli
fi
ln -sf /opt/oci-cli/bin/oci /usr/local/bin/oci

echo "Checking OCI Instance Principal authorization..."
NAMESPACE="$(oci os ns get --auth instance_principal --query data --raw-output)"
if [[ -z "$NAMESPACE" ]]; then echo "Cannot read Object Storage namespace; check IAM policy."; exit 1; fi
read -r -p "Existing private Object Storage bucket name: " BUCKET
if [[ ! "$BUCKET" =~ ^[a-zA-Z0-9._-]{1,256}$ ]]; then echo "Invalid bucket name."; exit 1; fi
oci os object list --auth instance_principal --namespace-name "$NAMESPACE" --bucket-name "$BUCKET" --limit 1 >/dev/null

APP_ENV=/etc/class-merit-hub/app.env
DB_PATH="$(grep '^DATABASE_PATH=' "$APP_ENV" | tail -n1 | cut -d= -f2-)"
RECIPIENT_FILE=/etc/class-merit-hub/backup-recipient.txt
if [[ ! -s "$RECIPIENT_FILE" ]]; then
  EXISTING_BACKUP_COUNT="$(
    oci os object list --auth instance_principal --namespace-name "$NAMESPACE" \
      --bucket-name "$BUCKET" --prefix class-merit-hub/ --all --output json \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(1 for x in d.get("data",[]) if x["name"].endswith(".sqlite3.gz.age")))'
  )"
  if (( EXISTING_BACKUP_COUNT > 0 )); then
    echo "Existing Class Merit Hub backups were found in this bucket."
    echo "To keep them decryptable, supply the OLD public age recipient from your offline copy."
    read -r -p "Existing age public recipient (age1...): " EXISTING_RECIPIENT
    if [[ ! "$EXISTING_RECIPIENT" =~ ^age1[a-z0-9]{40,}$ ]]; then
      echo "Invalid age recipient. Refusing to create a new key that cannot decrypt existing backups." >&2
      exit 1
    fi
    printf '%s\\n' "$EXISTING_RECIPIENT" > "$RECIPIENT_FILE"
    chmod 0640 "$RECIPIENT_FILE"
    chown root:root "$RECIPIENT_FILE"
  else
    age-keygen -o /root/class-merit-backup-identity.txt
    chmod 0600 /root/class-merit-backup-identity.txt
    age-keygen -y /root/class-merit-backup-identity.txt > "$RECIPIENT_FILE"
    chmod 0640 "$RECIPIENT_FILE"
    chown root:root "$RECIPIENT_FILE"
    echo "Created a new age key pair. Copy both the private identity and public recipient off the VM."
  fi
fi

cat > /etc/class-merit-hub/backup.env <<EOF
OCI_NAMESPACE=$NAMESPACE
OCI_BUCKET=$BUCKET
OCI_PREFIX=class-merit-hub/
DATABASE_PATH=$DB_PATH
AGE_RECIPIENT_FILE=$RECIPIENT_FILE
LOCAL_BACKUP_DIR=/var/backups/class-merit-hub
EOF
chown root:root /etc/class-merit-hub/backup.env
chmod 0600 /etc/class-merit-hub/backup.env

cat > /etc/systemd/system/class-merit-backup.service <<'EOF'
[Unit]
Description=Encrypted Class Merit Hub SQLite backup to OCI Object Storage
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/class-merit-backup
EOF

cat > /etc/systemd/system/class-merit-backup.timer <<'EOF'
[Unit]
Description=Daily Class Merit Hub backup
[Timer]
OnCalendar=*-*-* 19:30:00 UTC
RandomizedDelaySec=10m
Persistent=true
[Install]
WantedBy=timers.target
EOF

install -m 0750 -o root -g root deploy/oracle/backup.sh /usr/local/sbin/class-merit-backup
install -m 0750 -o root -g root deploy/oracle/verify_backup.sh /usr/local/sbin/class-merit-verify-backup
systemctl daemon-reload
systemctl enable --now class-merit-backup.timer
systemctl start class-merit-backup.service
echo "Daily backup scheduled at about 02:30 Vietnam time (UTC+7)."
echo "Check: systemctl list-timers class-merit-backup.timer"
