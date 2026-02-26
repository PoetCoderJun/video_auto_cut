#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${APP_DIR:-$ROOT_DIR}"
SERVICE_USER="${SERVICE_USER:-videoautocut}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
ENV_DIR="${ENV_DIR:-/etc/video-auto-cut}"
ENV_FILE="${ENV_FILE:-$ENV_DIR/video-auto-cut.env}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ENABLE_NOW="${ENABLE_NOW:-0}"

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "[install_systemd] sudo not found and current user is not root"
    exit 1
  fi
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "[install_systemd] systemctl not found"
  exit 1
fi

for svc in api worker frontend; do
  if [[ ! -f "$ROOT_DIR/deploy/systemd/video-auto-cut-${svc}.service" ]]; then
    echo "[install_systemd] missing template: deploy/systemd/video-auto-cut-${svc}.service"
    exit 1
  fi
done

if [[ ! -f "$ROOT_DIR/deploy/systemd/video-auto-cut.env.example" ]]; then
  echo "[install_systemd] missing template: deploy/systemd/video-auto-cut.env.example"
  exit 1
fi

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "[install_systemd] creating system user: $SERVICE_USER"
  $SUDO useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
  echo "[install_systemd] creating group: $SERVICE_GROUP"
  $SUDO groupadd --system "$SERVICE_GROUP"
fi

$SUDO mkdir -p "$ENV_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "[install_systemd] creating env file from template: $ENV_FILE"
  $SUDO cp "$ROOT_DIR/deploy/systemd/video-auto-cut.env.example" "$ENV_FILE"
  $SUDO chmod 640 "$ENV_FILE"
fi
$SUDO chown "$SERVICE_USER:$SERVICE_GROUP" "$ENV_FILE"

for svc in api worker frontend; do
  src="$ROOT_DIR/deploy/systemd/video-auto-cut-${svc}.service"
  dst="$SYSTEMD_DIR/video-auto-cut-${svc}.service"
  tmp="$(mktemp)"
  sed \
    -e "s|User=videoautocut|User=${SERVICE_USER}|" \
    -e "s|Group=videoautocut|Group=${SERVICE_GROUP}|" \
    -e "s|/opt/video_auto_cut|${APP_DIR}|g" \
    "$src" > "$tmp"
  echo "[install_systemd] installing service: $dst"
  $SUDO install -m 0644 "$tmp" "$dst"
  rm -f "$tmp"
done

$SUDO systemctl daemon-reload

if [[ "$ENABLE_NOW" == "1" || "$ENABLE_NOW" == "true" || "$ENABLE_NOW" == "yes" ]]; then
  $SUDO systemctl enable --now \
    video-auto-cut-api.service \
    video-auto-cut-worker.service \
    video-auto-cut-frontend.service
  echo "[install_systemd] services enabled and started"
else
  echo "[install_systemd] services installed"
  echo "[install_systemd] ensure user '$SERVICE_USER' has access to: $APP_DIR"
  echo "[install_systemd] edit env file first: $ENV_FILE"
  echo "[install_systemd] then run:"
  echo "  sudo systemctl enable --now video-auto-cut-api.service video-auto-cut-worker.service video-auto-cut-frontend.service"
fi
