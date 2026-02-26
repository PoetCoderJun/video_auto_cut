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

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
API_BROWSER_HOST="${API_BROWSER_HOST:-$API_HOST}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[start_web_prod] python not found: $PYTHON_BIN"
  echo "[start_web_prod] run ./scripts/install_ubuntu.sh first"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[start_web_prod] npm not found"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "[start_web_prod] ffmpeg/ffprobe missing"
  echo "[start_web_prod] run ./scripts/install_ubuntu.sh first"
  exit 1
fi

DB_LOCAL_ONLY_RAW="${WEB_DB_LOCAL_ONLY:-0}"
DB_LOCAL_ONLY="$(printf '%s' "$DB_LOCAL_ONLY_RAW" | tr '[:upper:]' '[:lower:]')"
if [[ "$DB_LOCAL_ONLY" != "1" && "$DB_LOCAL_ONLY" != "true" && "$DB_LOCAL_ONLY" != "yes" ]]; then
  if [[ -z "${TURSO_DATABASE_URL:-}" ]]; then
    echo "[start_web_prod] TURSO_DATABASE_URL is required (or set WEB_DB_LOCAL_ONLY=1)"
    exit 1
  fi
  if [[ -z "${TURSO_AUTH_TOKEN:-}" ]]; then
    echo "[start_web_prod] TURSO_AUTH_TOKEN is required (or set WEB_DB_LOCAL_ONLY=1)"
    exit 1
  fi
fi

AUTH_ENABLED_RAW="${WEB_AUTH_ENABLED:-1}"
AUTH_ENABLED="$(printf '%s' "$AUTH_ENABLED_RAW" | tr '[:upper:]' '[:lower:]')"
DEV_DEFAULT_SECRET="video-auto-cut-dev-better-auth-secret-change-me"
if [[ "$AUTH_ENABLED" == "1" || "$AUTH_ENABLED" == "true" || "$AUTH_ENABLED" == "yes" ]]; then
  auth_secret="${BETTER_AUTH_SECRET:-}"
  if [[ -z "$auth_secret" || "$auth_secret" == "$DEV_DEFAULT_SECRET" ]]; then
    echo "[start_web_prod] BETTER_AUTH_SECRET must be set to a strong non-default value"
    exit 1
  fi
  if [[ "${#auth_secret}" -lt 32 ]]; then
    echo "[start_web_prod] BETTER_AUTH_SECRET must be at least 32 characters in production"
    exit 1
  fi
fi

asr_backend="$(printf '%s' "${ASR_BACKEND:-dashscope_filetrans}" | tr '[:upper:]' '[:lower:]')"
if [[ "$asr_backend" == "dashscope_filetrans" ]]; then
  if [[ -z "${ASR_DASHSCOPE_API_KEY:-${DASHSCOPE_API_KEY:-}}" ]]; then
    echo "[start_web_prod] ASR_DASHSCOPE_API_KEY or DASHSCOPE_API_KEY is required when ASR_BACKEND=dashscope_filetrans"
    exit 1
  fi
  for key in OSS_ENDPOINT OSS_BUCKET OSS_ACCESS_KEY_ID OSS_ACCESS_KEY_SECRET; do
    if [[ -z "${!key:-}" ]]; then
      echo "[start_web_prod] $key is required when ASR_BACKEND=dashscope_filetrans"
      exit 1
    fi
  done
fi

SITE_URL_DEFAULT="http://127.0.0.1:${FRONTEND_PORT}"
export NODE_ENV="production"
export NEXT_PUBLIC_SITE_URL="${NEXT_PUBLIC_SITE_URL:-$SITE_URL_DEFAULT}"
export BETTER_AUTH_URL="${BETTER_AUTH_URL:-$NEXT_PUBLIC_SITE_URL}"
export WEB_AUTH_BASE_URL="${WEB_AUTH_BASE_URL:-$BETTER_AUTH_URL}"
export WEB_AUTH_ISSUER="${WEB_AUTH_ISSUER:-$BETTER_AUTH_URL}"
export WEB_AUTH_AUDIENCE="${WEB_AUTH_AUDIENCE:-$BETTER_AUTH_URL}"
export WEB_AUTH_JWKS_URL="${WEB_AUTH_JWKS_URL:-${BETTER_AUTH_URL%/}/api/auth/jwks}"
export NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://$API_BROWSER_HOST:$API_PORT/api/v1}"
export WEB_CORS_ALLOWED_ORIGINS="${WEB_CORS_ALLOWED_ORIGINS:-$NEXT_PUBLIC_SITE_URL}"

if [[ -n "${TURSO_LOCAL_REPLICA_PATH:-}" ]]; then
  API_REPLICA_DEFAULT="${TURSO_LOCAL_REPLICA_PATH}.api"
else
  API_REPLICA_DEFAULT="$ROOT_DIR/workdir/web_api_turso_replica_api.db"
fi
API_TURSO_LOCAL_REPLICA_PATH="${API_TURSO_LOCAL_REPLICA_PATH:-$API_REPLICA_DEFAULT}"
WORKER_TURSO_LOCAL_REPLICA_PATH="${WORKER_TURSO_LOCAL_REPLICA_PATH:-$API_TURSO_LOCAL_REPLICA_PATH}"

"$PYTHON_BIN" - <<'PY'
import importlib.util
import os

required = ["fastapi", "uvicorn", "multipart", "jwt", "libsql", "qwen_asr"]
asr_backend = (os.getenv("ASR_BACKEND") or "").strip().lower()
if asr_backend == "dashscope_filetrans":
    required.append("oss2")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(
        "[start_web_prod] missing python deps: "
        + ", ".join(missing)
        + " (run ./scripts/install_ubuntu.sh)"
    )
PY

if [[ ! -d "$ROOT_DIR/web_frontend/node_modules" ]]; then
  echo "[start_web_prod] installing frontend deps ..."
  npm --prefix "$ROOT_DIR/web_frontend" install
fi

if [[ "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
  echo "[start_web_prod] skip frontend build (SKIP_FRONTEND_BUILD=1)"
else
  echo "[start_web_prod] building frontend ..."
  npm --prefix "$ROOT_DIR/web_frontend" run build
fi

if [[ "$AUTH_ENABLED" == "1" || "$AUTH_ENABLED" == "true" || "$AUTH_ENABLED" == "yes" ]]; then
  echo "[start_web_prod] running Better Auth migrations ..."
  (cd "$ROOT_DIR/web_frontend" && npx @better-auth/cli migrate --config ./lib/auth.ts -y)
fi

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1
    return $?
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" | tail -n +2 | grep -q .
    return $?
  fi
  return 1
}

for port in "$API_PORT" "$FRONTEND_PORT"; do
  if port_in_use "$port"; then
    echo "[start_web_prod] port $port is already in use"
    exit 1
  fi
done

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
  echo "[start_web_prod] stopping services ..."
  for pid in "$FRONTEND_PID" "$WORKER_PID" "$API_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      sleep 0.2
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

echo "[start_web_prod] using python: $("$PYTHON_BIN" -c 'import sys; print(f"{sys.executable} (Python {sys.version.split()[0]})")')"
echo "[start_web_prod] starting FastAPI on $API_HOST:$API_PORT ..."
PYTHONUNBUFFERED=1 TURSO_LOCAL_REPLICA_PATH="$API_TURSO_LOCAL_REPLICA_PATH" \
  "$PYTHON_BIN" -m uvicorn web_api.app:app --host "$API_HOST" --port "$API_PORT" --log-level info --access-log &
API_PID=$!

echo "[start_web_prod] starting worker loop ..."
PYTHONUNBUFFERED=1 TURSO_LOCAL_REPLICA_PATH="$WORKER_TURSO_LOCAL_REPLICA_PATH" \
  "$PYTHON_BIN" -m web_api &
WORKER_PID=$!

echo "[start_web_prod] starting Next.js on $FRONTEND_HOST:$FRONTEND_PORT ..."
NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" \
  NEXT_PUBLIC_SITE_URL="$NEXT_PUBLIC_SITE_URL" \
  BETTER_AUTH_URL="$BETTER_AUTH_URL" \
  npm --prefix "$ROOT_DIR/web_frontend" run start -- -H "$FRONTEND_HOST" -p "$FRONTEND_PORT" &
FRONTEND_PID=$!

wait_http() {
  local url="$1"
  local retries="$2"

  for _ in $(seq 1 "$retries"); do
    if "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("$url", timeout=2)
PY
    then
      return 0
    fi
    sleep 1
  done

  return 1
}

if ! wait_http "http://$API_HOST:$API_PORT/healthz" 45; then
  echo "[start_web_prod] FastAPI did not become healthy in time"
  exit 1
fi

if ! wait_http "http://127.0.0.1:$FRONTEND_PORT" 75; then
  echo "[start_web_prod] frontend did not become healthy in time"
  exit 1
fi

echo ""
echo "[start_web_prod] services are ready"
echo "  Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "  API:      http://$API_HOST:$API_PORT"
echo "  Worker:   pid $WORKER_PID"
echo "  Health:   http://$API_HOST:$API_PORT/healthz"
echo ""
echo "[start_web_prod] logs are streaming in this terminal"
echo "[start_web_prod] press Ctrl+C to stop all services"

while true; do
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    echo "[start_web_prod] FastAPI exited unexpectedly"
    exit 1
  fi
  if ! kill -0 "$WORKER_PID" >/dev/null 2>&1; then
    echo "[start_web_prod] worker exited unexpectedly"
    exit 1
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "[start_web_prod] frontend exited unexpectedly"
    exit 1
  fi
  sleep 2
done
