#!/usr/bin/env bash
# Stop all Video Auto Cut services (systemd mode).
set -euo pipefail

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
fi

SERVICES=(
  video-auto-cut-frontend.service
  video-auto-cut-worker.service
  video-auto-cut-api.service
)

echo "[service_stop] stopping services ..."
$SUDO systemctl stop "${SERVICES[@]}"

echo ""
for svc in "${SERVICES[@]}"; do
  state="$($SUDO systemctl is-active "$svc" 2>/dev/null || true)"
  echo "[service_stop]   $svc → $state"
done

echo ""
echo "[service_stop] done (nginx kept running)"
