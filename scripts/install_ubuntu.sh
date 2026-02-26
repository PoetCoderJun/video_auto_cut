#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "[install_ubuntu] sudo not found and current user is not root"
    exit 1
  fi
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[install_ubuntu] apt-get not found. This script is for Ubuntu/Debian only."
  exit 1
fi

APT_PACKAGES=(
  ca-certificates
  curl
  gnupg
  lsb-release
  software-properties-common
  build-essential
  git
  ffmpeg
  python3
  python3-venv
  python3-pip
  pkg-config
  libsqlite3-dev
  lsof
  ripgrep
)

echo "[install_ubuntu] apt update ..."
$SUDO apt-get update -y

echo "[install_ubuntu] installing system packages ..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"

install_node() {
  local major
  major=""
  if command -v node >/dev/null 2>&1; then
    major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
  fi

  if [[ -n "$major" && "$major" -ge 20 ]]; then
    echo "[install_ubuntu] node $(node -v) already installed"
    return
  fi

  echo "[install_ubuntu] installing Node.js 20.x ..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO -E bash -
  $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
  echo "[install_ubuntu] node $(node -v), npm $(npm -v)"
}

install_node

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[install_ubuntu] creating virtualenv at $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "[install_ubuntu] installing python deps ..."
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo "[install_ubuntu] installing frontend deps ..."
npm --prefix "$ROOT_DIR/web_frontend" install

echo "[install_ubuntu] done"
echo "[install_ubuntu] next steps:"
echo "  1) cp .env.example .env  # or prepare your .env"
echo "  2) source $VENV_DIR/bin/activate"
echo "  3) ./scripts/start_web_prod.sh"
echo "  4) optional: ENABLE_NOW=1 ./scripts/install_systemd_services.sh"
