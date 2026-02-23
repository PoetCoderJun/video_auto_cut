#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
API_BROWSER_HOST="${API_BROWSER_HOST:-127.0.0.1}"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if ! command -v python >/dev/null 2>&1; then
  echo "[start_web_mvp] python not found in PATH"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[start_web_mvp] npm not found in PATH"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "[start_web_mvp] warning: ffmpeg/ffprobe not found. Step1/Render may fail."
fi

python - <<'PY'
import importlib.util
import subprocess
import sys

required = ["fastapi", "uvicorn", "multipart"]
missing = [name for name in required if importlib.util.find_spec(name) is None]

if missing:
    print("[start_web_mvp] installing python deps via requirements.txt ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
PY

if [[ ! -d "$ROOT_DIR/web_frontend/node_modules" ]]; then
  echo "[start_web_mvp] installing frontend deps ..."
  npm --prefix "$ROOT_DIR/web_frontend" install
fi

port_in_use() {
  local port="$1"
  if lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

if port_in_use "$API_PORT"; then
  echo "[start_web_mvp] port $API_PORT is already in use"
  lsof -iTCP:"$API_PORT" -sTCP:LISTEN
  exit 1
fi

if port_in_use "$FRONTEND_PORT"; then
  echo "[start_web_mvp] port $FRONTEND_PORT is already in use"
  lsof -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN
  exit 1
fi

API_PID=""
WORKER_PID=""
FRONTEND_PID=""
CLEANED_UP=0

cleanup() {
  if [[ "$CLEANED_UP" -eq 1 ]]; then
    return
  fi
  CLEANED_UP=1

  echo ""
  echo "[start_web_mvp] stopping services ..."

  for pid in "$FRONTEND_PID" "$WORKER_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.2
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

echo "[start_web_mvp] starting FastAPI on $API_HOST:$API_PORT ..."
PYTHONUNBUFFERED=1 python -m uvicorn web_api.app:app --host "$API_HOST" --port "$API_PORT" --log-level info --access-log &
API_PID=$!

echo "[start_web_mvp] starting worker ..."
PYTHONUNBUFFERED=1 python -m web_api.worker.runner &
WORKER_PID=$!

echo "[start_web_mvp] starting Next.js on :$FRONTEND_PORT ..."
NEXT_PUBLIC_API_BASE="http://$API_BROWSER_HOST:$API_PORT/api/v1" \
  npm --prefix "$ROOT_DIR/web_frontend" run dev -- -p "$FRONTEND_PORT" &
FRONTEND_PID=$!

wait_http() {
  local url="$1"
  local retries="$2"

  for _ in $(seq 1 "$retries"); do
    if python - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("$url", timeout=1)
PY
    then
      return 0
    fi
    sleep 1
  done

  return 1
}

if ! wait_http "http://$API_HOST:$API_PORT/healthz" 45; then
  echo "[start_web_mvp] FastAPI did not become healthy in time"
  exit 1
fi

if ! wait_http "http://127.0.0.1:$FRONTEND_PORT" 75; then
  echo "[start_web_mvp] frontend did not become healthy in time"
  exit 1
fi

echo ""
echo "[start_web_mvp] services are ready"
echo "  Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "  API:      http://$API_HOST:$API_PORT"
echo "  Health:   http://$API_HOST:$API_PORT/healthz"
echo ""
echo "[start_web_mvp] logs are streaming in this terminal"
echo "[start_web_mvp] press Ctrl+C to stop all services"

while true; do
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    echo "[start_web_mvp] FastAPI exited unexpectedly"
    exit 1
  fi
  if ! kill -0 "$WORKER_PID" >/dev/null 2>&1; then
    echo "[start_web_mvp] worker exited unexpectedly"
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "[start_web_mvp] frontend exited unexpectedly"
    exit 1
  fi
  sleep 2
done
