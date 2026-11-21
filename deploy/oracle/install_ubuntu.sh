#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/conmeophat/quan_ly_thanh_vien_trong-lop.git"
APP_DIR="/opt/class-merit-hub"
ETC_DIR="/etc/class-merit-hub"
DATA_MOUNT="/srv/class-merit-data"
APP_USER="classmerit"

if [[ "$EUID" -ne 0 ]]; then echo "Run with sudo."; exit 1; fi
if ! command -v apt-get >/dev/null 2>&1; then echo "Ubuntu is required."; exit 1; fi
if [[ "$( . /etc/os-release && echo "$VERSION_ID" )" != "24.04" ]]; then
  echo "Recommended OS is Ubuntu 24.04 LTS. Review before using another release."
fi
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

read -r -p "DuckDNS subdomain (without .duckdns.org): " DUCKDNS_DOMAIN
DUCKDNS_DOMAIN="$(echo "$DUCKDNS_DOMAIN" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
if [[ ! "$DUCKDNS_DOMAIN" =~ ^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$ ]]; then echo "Invalid subdomain."; exit 1; fi
DOMAIN="$DUCKDNS_DOMAIN.duckdns.org"
read -r -s -p "DuckDNS token (input hidden): " DUCKDNS_TOKEN
echo
TOKEN_LENGTH="$(printf '%s' "$DUCKDNS_TOKEN" | wc -c)"
if [[ "$TOKEN_LENGTH" -lt 16 ]]; then echo "Token looks too short."; exit 1; fi

echo "[1/8] Installing packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git gnupg age sqlite3 \
  python3 python3-venv python3-pip ufw fail2ban unattended-upgrades jq logrotate

echo "[2/8] Installing Caddy..."
install -d -m 0755 /usr/share/keyrings
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod 0644 /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
  -o /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

echo "[3/8] Fetching application..."
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" pull --ff-only origin main
else
  if [[ -e "$APP_DIR" ]]; then echo "$APP_DIR exists but is not a Git repository."; exit 1; fi
  git clone --depth 1 --branch main "$REPO_URL" "$APP_DIR"
fi
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[4/8] Preparing database storage..."
if mountpoint -q "$DATA_MOUNT"; then
  DB_DIR="$DATA_MOUNT"
  echo "Using Block Volume at $DATA_MOUNT."
else
  DB_DIR="/var/lib/class-merit-hub"
  echo "WARNING: No separate data volume detected; using persistent VM boot volume."
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$DB_DIR"
install -d -o root -g "$APP_USER" -m 0750 "$ETC_DIR"
install -d -o root -g root -m 0700 /var/backups/class-merit-hub

if [[ ! -f "$ETC_DIR/app.env" ]]; then
  STORAGE_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  BOOTSTRAP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$ETC_DIR/app.env" <<EOF
HOST=127.0.0.1
PORT=8080
COOKIE_SECURE=true
DATABASE_PATH=$DB_DIR/class_tracker.sqlite3
NICEGUI_STORAGE_SECRET=$STORAGE_SECRET
BOOTSTRAP_TOKEN=$BOOTSTRAP_TOKEN
EOF
  chown root:"$APP_USER" "$ETC_DIR/app.env"
  chmod 0640 "$ETC_DIR/app.env"
  printf '%s\n' "$BOOTSTRAP_TOKEN" > /root/class-merit-bootstrap-token.txt
  chmod 0600 /root/class-merit-bootstrap-token.txt
else
  echo "Existing app.env found. Keeping current secrets and database path unchanged."
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
chmod 0750 "$APP_DIR"

echo "[5/8] Creating systemd app service..."
cat > /etc/systemd/system/class-merit-hub.service <<EOF
[Unit]
Description=Class Merit Hub NiceGUI application
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ETC_DIR/app.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/main.py
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DB_DIR /var/log
UMask=0027

[Install]
WantedBy=multi-user.target
EOF

install -m 0750 -o root -g root "$APP_DIR/deploy/oracle/healthcheck.sh" /usr/local/sbin/class-merit-healthcheck

cat > /etc/systemd/system/class-merit-healthcheck.service <<'EOF'
[Unit]
Description=Class Merit Hub local health watchdog
After=class-merit-hub.service caddy.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/class-merit-healthcheck
EOF

cat > /etc/systemd/system/class-merit-healthcheck.timer <<'EOF'
[Unit]
Description=Check Class Merit Hub health every minute
[Timer]
OnBootSec=2min
OnUnitActiveSec=1min
Persistent=true
[Install]
WantedBy=timers.target
EOF

echo "[6/8] Configuring DuckDNS and HTTPS..."
cat > "$ETC_DIR/duckdns.env" <<EOF
DUCKDNS_DOMAIN=$DUCKDNS_DOMAIN
DUCKDNS_TOKEN=$DUCKDNS_TOKEN
EOF
chown root:root "$ETC_DIR/duckdns.env"
chmod 0600 "$ETC_DIR/duckdns.env"

cat > /usr/local/sbin/class-merit-duckdns-update <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
source /etc/class-merit-hub/duckdns.env
response="$(curl --fail --silent --show-error --get \
  --data-urlencode "domains=$DUCKDNS_DOMAIN" \
  --data-urlencode "token=$DUCKDNS_TOKEN" \
  https://www.duckdns.org/update)"
if [[ "$response" != "OK" ]]; then echo "DuckDNS update failed: $response" >&2; exit 1; fi
echo "DuckDNS record refreshed."
EOF
chmod 0750 /usr/local/sbin/class-merit-duckdns-update

cat > /etc/systemd/system/class-merit-duckdns.service <<'EOF'
[Unit]
Description=Refresh Class Merit Hub DuckDNS address
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/class-merit-duckdns-update
EOF

cat > /etc/systemd/system/class-merit-duckdns.timer <<'EOF'
[Unit]
Description=Refresh DuckDNS address every five minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Persistent=true
[Install]
WantedBy=timers.target
EOF

cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8080
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        X-Frame-Options DENY
        -Server
    }
    log {
        output file /var/log/caddy/class-merit-access.log {
            roll_size 10MiB
            roll_keep 5
            roll_keep_for 720h
        }
    }
}
EOF
mkdir -p /var/log/caddy
chown caddy:caddy /var/log/caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

echo "[7/8] Configuring firewall and security updates..."
read -r -p "SSH source CIDR (recommended: your public IP/32; blank = 0.0.0.0/0): " SSH_CIDR
if [[ -z "$SSH_CIDR" ]]; then SSH_CIDR="0.0.0.0/0"; fi
ufw allow from "$SSH_CIDR" to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban
systemctl enable --now apt-daily-upgrade.timer

echo "[8/8] Starting services..."
systemctl daemon-reload
systemctl enable --now class-merit-hub.service
systemctl enable --now class-merit-healthcheck.timer
systemctl enable --now class-merit-duckdns.timer
/usr/local/sbin/class-merit-duckdns-update
systemctl enable caddy
systemctl restart caddy

echo
echo "Domain: https://$DOMAIN"
echo "Health check: https://$DOMAIN/healthz"
echo "App: journalctl -u class-merit-hub -n 100 --no-pager"
echo "Caddy: journalctl -u caddy -n 100 --no-pager"
if [[ -f /root/class-merit-bootstrap-token.txt ]]; then
  echo "One-time founder token: sudo cat /root/class-merit-bootstrap-token.txt"
  echo "Delete that file after creating the founder account. Never paste it into chat or GitHub."
fi
echo "IMPORTANT: Open TCP 80/443 in the OCI NSG/Security List; restrict TCP 22 to your own IP."
