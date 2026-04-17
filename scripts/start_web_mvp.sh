#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE_RAW="${1:-${WEB_MVP_MODE:-build}}"
MODE="$(printf '%s' "$MODE_RAW" | tr '[:upper:]' '[:lower:]')"
case "$MODE" in
  build|prod|production)
    MODE="build"
    ;;
  debug|dev)
    MODE="debug"
    ;;
  *)
    echo "usage: $0 [debug|build]"
    echo "[start_web_mvp] unsupported mode: $MODE_RAW"
    exit 2
    ;;
esac

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
API_BROWSER_HOST="${API_BROWSER_HOST:-127.0.0.1}"
PYTHON_BIN="${PYTHON_BIN:-python}"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ -z "${TURSO_DATABASE_URL:-}" ]]; then
  echo "[start_web_mvp] TURSO_DATABASE_URL is required"
  exit 1
fi

if [[ -z "${TURSO_AUTH_TOKEN:-}" ]]; then
  echo "[start_web_mvp] TURSO_AUTH_TOKEN is required"
  exit 1
fi

echo "[start_web_mvp] Turso replica mode enabled"

SHARED_REPLICA_DEFAULT="${TURSO_LOCAL_REPLICA_PATH:-$ROOT_DIR/workdir/web_api_turso_replica.db}"
API_TURSO_LOCAL_REPLICA_PATH="${API_TURSO_LOCAL_REPLICA_PATH:-$SHARED_REPLICA_DEFAULT}"

LEGACY_REPLICA_FILES=(
  "${TURSO_LOCAL_REPLICA_PATH:-$ROOT_DIR/workdir/web_api_turso_replica.db}.api"
  "${TURSO_LOCAL_REPLICA_PATH:-$ROOT_DIR/workdir/web_api_turso_replica.db}.worker"
  "$ROOT_DIR/workdir/web_api_turso_replica.db.api"
  "$ROOT_DIR/workdir/web_api_turso_replica.db.worker"
)

AUTH_ENABLED_RAW="${WEB_AUTH_ENABLED:-1}"
AUTH_ENABLED="$(printf '%s' "$AUTH_ENABLED_RAW" | tr '[:upper:]' '[:lower:]')"
if [[ "$AUTH_ENABLED" == "1" || "$AUTH_ENABLED" == "true" || "$AUTH_ENABLED" == "yes" ]]; then
  if [[ -z "${BETTER_AUTH_SECRET:-}" ]]; then
    export BETTER_AUTH_SECRET="video-auto-cut-local-prod-secret-please-change-2026"
    echo "[start_web_mvp] warning: BETTER_AUTH_SECRET is empty, using generated local production secret"
  fi
fi

SITE_URL_DEFAULT="http://127.0.0.1:${FRONTEND_PORT}"
export NEXT_PUBLIC_SITE_URL="${NEXT_PUBLIC_SITE_URL:-$SITE_URL_DEFAULT}"
export BETTER_AUTH_URL="${BETTER_AUTH_URL:-$SITE_URL_DEFAULT}"
export WEB_API_BASE="${WEB_API_BASE:-http://$API_BROWSER_HOST:$API_PORT/api/v1}"
export WEB_AUTH_BASE_URL="${WEB_AUTH_BASE_URL:-$BETTER_AUTH_URL}"
export WEB_AUTH_ISSUER="${WEB_AUTH_ISSUER:-$BETTER_AUTH_URL}"
export WEB_AUTH_AUDIENCE="${WEB_AUTH_AUDIENCE:-$BETTER_AUTH_URL}"
export WEB_AUTH_JWKS_URL="${WEB_AUTH_JWKS_URL:-${BETTER_AUTH_URL%/}/api/auth/jwks}"
ASR_BACKEND_NORMALIZED="$(printf '%s' "${ASR_BACKEND:-dashscope_filetrans}" | tr '[:upper:]' '[:lower:]')"
if [[ "$ASR_BACKEND_NORMALIZED" != "dashscope_filetrans" ]]; then
  echo "[start_web_mvp] unsupported ASR_BACKEND=$ASR_BACKEND_NORMALIZED (only dashscope_filetrans is supported)"
  exit 1
fi

python_can_run() {
  "$@" - <<'PY' >/dev/null 2>&1
import sys
ok = sys.version_info >= (3, 10)
raise SystemExit(0 if ok else 1)
PY
}

PYTHON_CMD=("$PYTHON_BIN")

if ! command -v "${PYTHON_CMD[0]}" >/dev/null 2>&1; then
  echo "[start_web_mvp] python not found: ${PYTHON_CMD[0]}"
  exit 1
fi

if ! python_can_run "${PYTHON_CMD[@]}"; then
  if command -v conda >/dev/null 2>&1 && python_can_run conda run --no-capture-output -n qwen312 python; then
    echo "[start_web_mvp] current python cannot run test flow (Python>=3.10), fallback to conda env: qwen312"
    PYTHON_CMD=(conda run --no-capture-output -n qwen312 python)
  else
    echo "[start_web_mvp] current python cannot run test flow (requires Python>=3.10)."
    echo "[start_web_mvp] fix: activate a compatible env or set PYTHON_BIN."
    exit 1
  fi
fi

echo "[start_web_mvp] using python: $("${PYTHON_CMD[@]}" -c 'import sys; print(f"{sys.executable} (Python {sys.version.split()[0]})")')"
echo "[start_web_mvp] frontend mode: $MODE"
echo "[start_web_mvp] business DB path: $API_TURSO_LOCAL_REPLICA_PATH"

legacy_replica_detected=0
for legacy_replica in "${LEGACY_REPLICA_FILES[@]}"; do
  if [[ "$legacy_replica" != "$API_TURSO_LOCAL_REPLICA_PATH" && -f "$legacy_replica" ]]; then
    legacy_replica_detected=1
    break
  fi
done
if [[ "$legacy_replica_detected" -eq 1 ]]; then
  echo "[start_web_mvp] note: legacy local replica files (.api/.worker) were detected and will be ignored"
  echo "[start_web_mvp] note: local development now maintains a single business DB at $API_TURSO_LOCAL_REPLICA_PATH"
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[start_web_mvp] npm not found in PATH"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "[start_web_mvp] warning: ffmpeg/ffprobe not found. test flow/render may fail."
fi

"${PYTHON_CMD[@]}" - <<'PY'
import importlib.util
import os
import subprocess
import sys

required = ["fastapi", "uvicorn", "multipart", "jwt"]
required.append("libsql")
asr_backend = (os.getenv("ASR_BACKEND") or "").strip().lower()
if asr_backend == "dashscope_filetrans":
    required.append("oss2")
missing = [name for name in required if importlib.util.find_spec(name) is None]

if missing:
    print(f"[start_web_mvp] missing python deps: {', '.join(missing)}")
    print("[start_web_mvp] installing python deps via requirements.txt ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

if asr_backend == "dashscope_filetrans" and importlib.util.find_spec("oss2") is None:
    raise SystemExit("[start_web_mvp] oss2 still missing after dependency install.")
PY

if [[ ! -d "$ROOT_DIR/web_frontend/node_modules" ]]; then
  echo "[start_web_mvp] installing frontend deps ..."
  npm --prefix "$ROOT_DIR/web_frontend" install
fi

if [[ "$AUTH_ENABLED" == "1" || "$AUTH_ENABLED" == "true" || "$AUTH_ENABLED" == "yes" ]]; then
  echo "[start_web_mvp] running Better Auth migrations ..."
  (cd "$ROOT_DIR/web_frontend" && npx @better-auth/cli migrate --config ./lib/auth.ts -y)
fi

existing_next_process="$(ps -ax -o pid=,command= | rg "next (dev|start)|\\.next/standalone/server\\.js" | rg "$ROOT_DIR/web_frontend" || true)"
if [[ -n "$existing_next_process" ]]; then
  echo "[start_web_mvp] detected existing Next.js process under web_frontend:"
  echo "$existing_next_process"
  echo "[start_web_mvp] stop it first, then rerun this script."
  exit 1
fi

existing_web_api_processes="$(ps -ax -o pid=,command= | rg 'uvicorn web_api.app:app' | rg -v 'start_web_mvp.sh|rg ' || true)"
if [[ -n "$existing_web_api_processes" ]]; then
  echo "[start_web_mvp] detected existing web_api processes:"
  echo "$existing_web_api_processes"
  echo "[start_web_mvp] stop them first, then rerun this script."
  exit 1
fi

next_lock_file="$ROOT_DIR/web_frontend/.next/dev/lock"
if [[ -f "$next_lock_file" ]]; then
  echo "[start_web_mvp] removing stale Next.js lock: $next_lock_file"
  rm -f "$next_lock_file"
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

if [[ "$MODE" == "build" ]]; then
  echo "[start_web_mvp] building Next.js production bundle ..."
  NEXT_PUBLIC_API_BASE="$WEB_API_BASE" \
  NEXT_PUBLIC_SITE_URL="$NEXT_PUBLIC_SITE_URL" \
  BETTER_AUTH_URL="$BETTER_AUTH_URL" \
  WEB_API_BASE="$WEB_API_BASE" \
    npm --prefix "$ROOT_DIR/web_frontend" run build

  echo "[start_web_mvp] syncing standalone static assets ..."
  mkdir -p "$ROOT_DIR/web_frontend/.next/standalone/.next"
  rm -rf "$ROOT_DIR/web_frontend/.next/standalone/public"
  cp -R "$ROOT_DIR/web_frontend/public" "$ROOT_DIR/web_frontend/.next/standalone/public"
  rm -rf "$ROOT_DIR/web_frontend/.next/standalone/.next/static"
  cp -R "$ROOT_DIR/web_frontend/.next/static" "$ROOT_DIR/web_frontend/.next/standalone/.next/static"
fi

API_PID=""
FRONTEND_PID=""
CLEANED_UP=0

cleanup() {
  if [[ "$CLEANED_UP" -eq 1 ]]; then
    return
  fi
  CLEANED_UP=1

  echo ""
  echo "[start_web_mvp] stopping services ..."

  for pid in "$FRONTEND_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.2
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

echo "[start_web_mvp] starting FastAPI on $API_HOST:$API_PORT ..."
PYTHONUNBUFFERED=1 TURSO_LOCAL_REPLICA_PATH="$API_TURSO_LOCAL_REPLICA_PATH" \
  "${PYTHON_CMD[@]}" -m uvicorn web_api.app:app --host "$API_HOST" --port "$API_PORT" --log-level info --access-log &
API_PID=$!

if [[ "$MODE" == "debug" ]]; then
  echo "[start_web_mvp] starting Next.js debug server on 127.0.0.1:$FRONTEND_PORT ..."
  NEXT_PUBLIC_API_BASE="http://$API_BROWSER_HOST:$API_PORT/api/v1" \
    NEXT_PUBLIC_SITE_URL="$NEXT_PUBLIC_SITE_URL" \
    BETTER_AUTH_URL="$BETTER_AUTH_URL" \
    WEB_API_BASE="http://$API_BROWSER_HOST:$API_PORT/api/v1" \
    npm --prefix "$ROOT_DIR/web_frontend" run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT" &
  FRONTEND_PID=$!
else
  echo "[start_web_mvp] starting Next.js production server on :$FRONTEND_PORT ..."
  NEXT_PUBLIC_API_BASE="http://$API_BROWSER_HOST:$API_PORT/api/v1" \
    NEXT_PUBLIC_SITE_URL="$NEXT_PUBLIC_SITE_URL" \
    BETTER_AUTH_URL="$BETTER_AUTH_URL" \
    WEB_API_BASE="http://$API_BROWSER_HOST:$API_PORT/api/v1" \
    HOSTNAME="127.0.0.1" \
    PORT="$FRONTEND_PORT" \
    bash -lc 'cd "$1/web_frontend" && exec node .next/standalone/server.js' _ "$ROOT_DIR" &
  FRONTEND_PID=$!
fi

wait_http() {
  local url="$1"
  local retries="$2"

  for _ in $(seq 1 "$retries"); do
    if "${PYTHON_CMD[@]}" - <<PY >/dev/null 2>&1
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
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "[start_web_mvp] frontend exited unexpectedly"
    exit 1
  fi
  sleep 2
done
