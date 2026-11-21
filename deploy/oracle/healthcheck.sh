#!/usr/bin/env bash
set -Eeuo pipefail

APP_URL="http://127.0.0.1:8080/healthz"
if ! curl --fail --silent --show-error --max-time 10 "$APP_URL" >/dev/null 2>&1; then
  logger -t class-merit-health "App health check failed; attempting one systemd restart."
  systemctl restart class-merit-hub
  sleep 5
  if ! curl --fail --silent --show-error --max-time 10 "$APP_URL" >/dev/null 2>&1; then
    logger -t class-merit-health "App still unhealthy after restart; manual review required."
    exit 1
  fi
fi

if ! systemctl is-active --quiet caddy; then
  logger -t class-merit-health "Caddy is not active; attempting restart."
  systemctl restart caddy
fi

echo "Application and reverse-proxy health checks passed."
