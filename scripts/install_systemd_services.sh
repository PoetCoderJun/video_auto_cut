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

NGINX_SERVER_NAME="${NGINX_SERVER_NAME:-_}"
NGINX_API_PORT="${NGINX_API_PORT:-8000}"
NGINX_FRONTEND_PORT="${NGINX_FRONTEND_PORT:-3000}"
NGINX_SITES_AVAILABLE="${NGINX_SITES_AVAILABLE:-/etc/nginx/sites-available}"
NGINX_SITES_ENABLED="${NGINX_SITES_ENABLED:-/etc/nginx/sites-enabled}"

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

if [[ ! -f "$ROOT_DIR/deploy/nginx/video-auto-cut.conf" ]]; then
  echo "[install_systemd] missing template: deploy/nginx/video-auto-cut.conf"
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

# ---- Nginx config ----
if command -v nginx >/dev/null 2>&1; then
  nginx_conf_src="$ROOT_DIR/deploy/nginx/video-auto-cut.conf"
  nginx_conf_dst="$NGINX_SITES_AVAILABLE/video-auto-cut"
  nginx_conf_tmp="$(mktemp)"
  sed \
    -e "s|__SERVER_NAME__|${NGINX_SERVER_NAME}|g" \
    -e "s|__API_PORT__|${NGINX_API_PORT}|g" \
    -e "s|__FRONTEND_PORT__|${NGINX_FRONTEND_PORT}|g" \
    "$nginx_conf_src" > "$nginx_conf_tmp"
  echo "[install_systemd] installing nginx config: $nginx_conf_dst"
  $SUDO install -m 0644 "$nginx_conf_tmp" "$nginx_conf_dst"
  rm -f "$nginx_conf_tmp"

  # Enable site (symlink into sites-enabled)
  if [[ ! -L "$NGINX_SITES_ENABLED/video-auto-cut" ]]; then
    $SUDO ln -sf "$nginx_conf_dst" "$NGINX_SITES_ENABLED/video-auto-cut"
    echo "[install_systemd] enabled nginx site: video-auto-cut"
  fi

  # Remove default nginx site to avoid port 80 conflict
  if [[ -L "$NGINX_SITES_ENABLED/default" ]]; then
    $SUDO rm -f "$NGINX_SITES_ENABLED/default"
    echo "[install_systemd] removed nginx default site"
  fi

  # Validate config
  if ! $SUDO nginx -t 2>/dev/null; then
    echo "[install_systemd] nginx config test failed — check $nginx_conf_dst"
    exit 1
  fi

  if [[ "$ENABLE_NOW" == "1" || "$ENABLE_NOW" == "true" || "$ENABLE_NOW" == "yes" ]]; then
    $SUDO systemctl enable --now nginx
    $SUDO systemctl reload nginx
    echo "[install_systemd] nginx enabled and reloaded"
  else
    echo "[install_systemd] nginx config installed (nginx not yet reloaded)"
    echo "[install_systemd] reload manually: sudo systemctl enable --now nginx && sudo nginx -s reload"
  fi
else
  echo "[install_systemd] warning: nginx not found, skipping nginx config install"
  echo "[install_systemd] install nginx first: sudo apt-get install -y nginx"
fi

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
