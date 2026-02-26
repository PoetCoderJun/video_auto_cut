#!/usr/bin/env bash
# Set up HTTPS for Video Auto Cut.
#
# Usage:
#   # Self-signed cert (no domain, browser will warn):
#   ./scripts/install_https.sh
#
#   # Let's Encrypt (requires a real domain pointing to this server):
#   DOMAIN=your-domain.example EMAIL=you@example.com ./scripts/install_https.sh
#
# Env vars:
#   DOMAIN            Domain name (default: server IP, uses self-signed cert)
#   EMAIL             Email for Let's Encrypt (required when DOMAIN is set)
#   API_PORT          FastAPI port (default: 8000)
#   FRONTEND_PORT     Next.js port (default: 3000)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
SSL_DIR="/etc/ssl/video-auto-cut"
NGINX_CONF_SRC="$ROOT_DIR/deploy/nginx/video-auto-cut-ssl.conf"
NGINX_CONF_DST="$NGINX_SITES_AVAILABLE/video-auto-cut"

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  SUDO="sudo"
fi

if [[ ! -f "$NGINX_CONF_SRC" ]]; then
  echo "[install_https] missing template: deploy/nginx/video-auto-cut-ssl.conf"
  exit 1
fi

# ---- Determine server name ----
if [[ -z "$DOMAIN" ]]; then
  # Fall back to public IP as server_name (self-signed)
  SERVER_NAME="$(curl -sf --max-time 5 https://ipv4.icanhazip.com || true)"
  if [[ -z "$SERVER_NAME" ]]; then
    SERVER_NAME="_"
  fi
  USE_CERTBOT=0
  echo "[install_https] no DOMAIN set — using self-signed certificate (server: ${SERVER_NAME})"
else
  SERVER_NAME="$DOMAIN"
  USE_CERTBOT=1
  echo "[install_https] domain: $DOMAIN — using Let's Encrypt"
fi

# ---- Self-signed certificate ----
install_self_signed() {
  $SUDO mkdir -p "$SSL_DIR"
  local cert="$SSL_DIR/cert.pem"
  local key="$SSL_DIR/key.pem"

  if [[ -f "$cert" && -f "$key" ]]; then
    echo "[install_https] self-signed cert already exists at $cert"
  else
    echo "[install_https] generating self-signed certificate ..."
    $SUDO openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout "$key" \
      -out "$cert" \
      -subj "/CN=${SERVER_NAME}/O=VideoAutoCut/C=CN"
    $SUDO chmod 600 "$key"
    echo "[install_https] certificate: $cert"
    echo "[install_https] key:         $key"
  fi

  SSL_CERT="$cert"
  SSL_KEY="$key"
}

# ---- Let's Encrypt certificate ----
install_certbot() {
  if [[ -z "$EMAIL" ]]; then
    echo "[install_https] EMAIL is required for Let's Encrypt"
    echo "[install_https] usage: EMAIL=you@example.com DOMAIN=$DOMAIN ./scripts/install_https.sh"
    exit 1
  fi

  if ! command -v certbot >/dev/null 2>&1; then
    echo "[install_https] installing certbot ..."
    $SUDO apt-get update -y
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx
  fi

  # Temporarily allow HTTP for ACME challenge
  echo "[install_https] obtaining Let's Encrypt certificate for $DOMAIN ..."
  $SUDO certbot certonly --nginx \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN"

  SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
  SSL_KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
  echo "[install_https] certificate: $SSL_CERT"
}

# ---- Obtain certificate ----
if [[ "$USE_CERTBOT" == "1" ]]; then
  install_certbot
else
  install_self_signed
fi

# ---- Write nginx SSL config ----
echo "[install_https] writing nginx SSL config: $NGINX_CONF_DST"
tmp="$(mktemp)"
sed \
  -e "s|__SERVER_NAME__|${SERVER_NAME}|g" \
  -e "s|__SSL_CERT__|${SSL_CERT}|g" \
  -e "s|__SSL_KEY__|${SSL_KEY}|g" \
  -e "s|__API_PORT__|${API_PORT}|g" \
  -e "s|__FRONTEND_PORT__|${FRONTEND_PORT}|g" \
  "$NGINX_CONF_SRC" > "$tmp"
$SUDO install -m 0644 "$tmp" "$NGINX_CONF_DST"
rm -f "$tmp"

# Ensure site is enabled
if [[ ! -L "$NGINX_SITES_ENABLED/video-auto-cut" ]]; then
  $SUDO ln -sf "$NGINX_CONF_DST" "$NGINX_SITES_ENABLED/video-auto-cut"
fi

# Remove default nginx site
if [[ -L "$NGINX_SITES_ENABLED/default" ]]; then
  $SUDO rm -f "$NGINX_SITES_ENABLED/default"
fi

# Validate and reload
if ! $SUDO nginx -t; then
  echo "[install_https] nginx config test failed — check $NGINX_CONF_DST"
  exit 1
fi

$SUDO systemctl enable --now nginx
$SUDO systemctl reload nginx

echo ""
echo "[install_https] HTTPS is ready"
if [[ "$USE_CERTBOT" == "1" ]]; then
  echo "  URL: https://$DOMAIN"
  echo "  note: certbot auto-renew is set up via systemd timer"
else
  echo "  URL: https://${SERVER_NAME}"
  echo "  note: self-signed cert — browser will show a security warning"
  echo "        accept it once, or press 'Advanced → Proceed' in Chrome"
  echo "        switch to a real cert later: DOMAIN=your-domain.example EMAIL=you@example.com ./scripts/install_https.sh"
fi

# ---- Also open port 443 reminder ----
echo ""
echo "[install_https] make sure port 443 is open in your cloud security group"
