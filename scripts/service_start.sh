#!/usr/bin/env bash
# Start all Video Auto Cut services (systemd mode).
# Prerequisite: run install_systemd_services.sh once first.
set -euo pipefail

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
fi

SERVICES=(
  video-auto-cut-api.service
  video-auto-cut-worker.service
  video-auto-cut-frontend.service
)

echo "[service_start] starting services ..."
$SUDO systemctl start "${SERVICES[@]}"

echo "[service_start] waiting for services to settle ..."
sleep 2

ALL_OK=1
for svc in "${SERVICES[@]}"; do
  state="$($SUDO systemctl is-active "$svc" 2>/dev/null || true)"
  if [[ "$state" == "active" ]]; then
    echo "[service_start]   ✓ $svc"
  else
    echo "[service_start]   ✗ $svc ($state)"
    ALL_OK=0
  fi
done

nginx_state="$($SUDO systemctl is-active nginx 2>/dev/null || true)"
if [[ "$nginx_state" == "active" ]]; then
  echo "[service_start]   ✓ nginx"
else
  echo "[service_start]   ! nginx ($nginx_state) — try: sudo systemctl start nginx"
fi

echo ""
if [[ "$ALL_OK" == "1" ]]; then
  echo "[service_start] all services running"
  echo "[service_start] logs: journalctl -u video-auto-cut-api -u video-auto-cut-worker -u video-auto-cut-frontend -f"
else
  echo "[service_start] some services failed — check with: journalctl -u <service-name> -n 50"
  exit 1
fi
