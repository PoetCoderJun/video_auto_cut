from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from .config import get_settings

try:
    import libsql  # type: ignore
except Exception:  # pragma: no cover - optional dependency for Turso mode
    libsql = None


_RetryFn = TypeVar("_RetryFn", bound=Callable[..., Any])
_TURSO_MARKERS = ("hrana", "libsql", "turso")
_TURSO_TRANSIENT_SIGNALS = (
    "404 not found",
    "500 internal server error",
    "502 bad gateway",
    "503 service unavailable",
    "504 gateway timeout",
    "broken pipe",
    "connection closed",
    "connection reset",
    "deadline has elapsed",
    "network error",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "unexpected eof",
)
_TURSO_CONNECT_ONLY_SIGNALS = (
    "error trying to connect",
    "tls handshake eof",
)


def _is_turso_enabled() -> bool:
    settings = get_settings()
    return bool(settings.turso_database_url and settings.turso_auth_token)


def is_turso_enabled() -> bool:
    return _is_turso_enabled()


def _extract_column_names(rows: list[Any]) -> set[str]:
    columns: set[str] = set()
    for row in rows:
        if isinstance(row, sqlite3.Row):
            try:
                columns.add(str(row["name"]))
                continue
            except Exception:
                pass
        if isinstance(row, dict):
            value = row.get("name")
            if value is not None:
                columns.add(str(value))
                continue
        try:
            columns.add(str(row[1]))
            continue
        except Exception:
            logging.debug("[web_api] failed to parse PRAGMA row: %r", row)
    return columns


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _create_local_conn() -> sqlite3.Connection:
    settings = get_settings()
    settings.turso_local_replica_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.turso_local_replica_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def _is_wal_conflict_error(exc: Exception) -> bool:
    message = str(exc or "")
    normalized = message.lower()
    return "wal frame insert conflict" in normalized or "walconflict" in normalized


def _is_invalid_local_replica_state_error(exc: Exception) -> bool:
    message = str(exc or "")
    normalized = message.lower()
    return (
        "invalid local state" in normalized
        or "metadata file does not exist" in normalized
        or "metadata file missing" in normalized
        or "db file exists but metadata file does not" in normalized
    )


def _should_reset_local_replica(exc: Exception) -> bool:
    return _is_wal_conflict_error(exc) or _is_invalid_local_replica_state_error(exc)


def _normalized_error_text(exc: Exception) -> str:
    normalized = str(exc or "").strip().lower()
    return normalized


def _is_retryable_turso_error_text(
    exc: Exception,
    *,
    require_turso_marker: bool,
    extra_signals: tuple[str, ...] = (),
) -> bool:
    if not _is_turso_enabled():
        return False

    normalized = _normalized_error_text(exc)
    if not normalized:
        return False
    if "stream not found" in normalized:
        return True

    if require_turso_marker and not any(marker in normalized for marker in _TURSO_MARKERS):
        return False

    return any(
        signal in normalized for signal in (_TURSO_TRANSIENT_SIGNALS + extra_signals)
    )


def is_retryable_turso_error(exc: Exception) -> bool:
    return _is_retryable_turso_error_text(exc, require_turso_marker=True)


def is_retryable_turso_connect_error(exc: Exception) -> bool:
    if is_retryable_turso_error(exc):
        return True
    return _is_retryable_turso_error_text(
        exc,
        require_turso_marker=False,
        extra_signals=_TURSO_CONNECT_ONLY_SIGNALS,
    )


def retry_turso_operation(
    operation_name: str,
    fn: _RetryFn | None = None,
    *,
    max_attempts: int = 2,
    base_delay_seconds: float = 0.15,
) -> _RetryFn | Callable[[_RetryFn], _RetryFn]:
    def decorator(inner: _RetryFn) -> _RetryFn:
        @wraps(inner)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            attempt = 1
            while True:
                try:
                    return inner(*args, **kwargs)
                except Exception as exc:
                    if attempt >= max(1, int(max_attempts)) or not is_retryable_turso_error(exc):
                        raise
                    logging.warning(
                        "[web_api] transient Turso error during %s attempt=%s/%s: %s",
                        operation_name,
                        attempt,
                        max_attempts,
                        exc,
                    )
                    time.sleep(max(0.0, float(base_delay_seconds)) * attempt)
                    attempt += 1

        return wrapped  # type: ignore[return-value]

    if fn is not None:
        return decorator(fn)
    return decorator


CURRENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_COUPON',
    activated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coupon_codes (
    coupon_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    credits INTEGER NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    status TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_ledger (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    job_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public_invite_claims (
    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_hash TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public_invite_settings (
    settings_id INTEGER PRIMARY KEY CHECK (settings_id = 1),
    max_claims INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coupon_codes_status_created_at
ON coupon_codes(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coupon_codes_source
ON coupon_codes(source);

CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created_at
ON credit_ledger(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_public_invite_claims_created_at
ON public_invite_claims(created_at DESC);
"""


def _replica_related_paths(replica_path: Path) -> list[Path]:
    return [
        replica_path,
        replica_path.with_name(replica_path.name + "-wal"),
        replica_path.with_name(replica_path.name + "-shm"),
        replica_path.with_name(replica_path.name + "-info"),
    ]


def _reset_local_replica(replica_path: Path) -> None:
    for path in _replica_related_paths(replica_path):
        try:
            if path.exists():
                path.unlink()
        except FileNotFoundError:
            continue


def _connect_turso(settings: Any) -> Any:
    if libsql is None:
        raise RuntimeError("Turso mode requires 'libsql'. Install with `pip install -r requirements.txt`.")
    if not settings.turso_database_url:
        raise RuntimeError("TURSO_DATABASE_URL is required. Example: libsql://<db>-<org>.turso.io")
    if not settings.turso_auth_token:
        raise RuntimeError("TURSO_AUTH_TOKEN is required.")

    connect_kwargs: dict[str, Any] = {
        "sync_url": settings.turso_database_url,
        "auth_token": settings.turso_auth_token,
    }
    if settings.turso_sync_interval > 0:
        connect_kwargs["sync_interval"] = settings.turso_sync_interval

    conn = libsql.connect(str(settings.turso_local_replica_path), **connect_kwargs)
    try:
        conn.row_factory = sqlite3.Row
    except Exception:
        pass
    return conn


def _create_conn() -> Any:
    settings = get_settings()
    if not settings.turso_database_url or not settings.turso_auth_token:
        return _create_local_conn()
    reset_reason = "unknown local replica issue"
    try:
        conn = _connect_turso(settings)
        try:
            _sync_best_effort(conn, stage="open", raise_on_error=True)
            return conn
        except Exception as exc:
            if is_retryable_turso_connect_error(exc):
                logging.warning(
                    "[web_api] Turso sync unavailable at open; continuing with local replica %s: %s",
                    settings.turso_local_replica_path,
                    exc,
                )
                return conn
            conn.close()
            if not _should_reset_local_replica(exc):
                raise RuntimeError(f"Turso connect failed: {exc}") from exc
            reset_reason = "WAL conflict" if _is_wal_conflict_error(exc) else "invalid local replica state"
    except Exception as exc:
        if not _should_reset_local_replica(exc):
            raise RuntimeError(f"Turso connect failed: {exc}") from exc
        reset_reason = "WAL conflict" if _is_wal_conflict_error(exc) else "invalid local replica state"

    logging.warning(
        "[web_api] detected %s for local replica %s, resetting and retrying once",
        reset_reason,
        settings.turso_local_replica_path,
    )
    _reset_local_replica(settings.turso_local_replica_path)
    try:
        conn = _connect_turso(settings)
        _sync_best_effort(conn, stage="open", raise_on_error=True)
        return conn
    except Exception as exc:
        raise RuntimeError(f"Turso connect failed after replica reset: {exc}") from exc


def _sync_best_effort(conn: Any, *, stage: str, raise_on_error: bool = False) -> None:
    if not hasattr(conn, "sync"):
        return
    try:
        conn.sync()
    except Exception as exc:
        logging.warning("[web_api] turso sync failed at %s: %s", stage, exc)
        if raise_on_error:
            raise


def _executescript(conn: Any, script: str) -> None:
    for statement in script.split(";"):
        sql = statement.strip()
        if not sql:
            continue
        conn.execute(sql)


@contextmanager
def get_conn() -> Iterator[Any]:
    conn = _create_conn()
    turso_enabled = _is_turso_enabled()
    try:
        yield conn
        if turso_enabled and hasattr(conn, "sync"):
            _sync_best_effort(conn, stage="close")
    finally:
        conn.close()


def ensure_current_schema(conn: Any) -> None:
    _executescript(conn, CURRENT_SCHEMA_SQL)
    conn.execute(
        """
        INSERT OR IGNORE INTO public_invite_settings(settings_id, max_claims, created_at, updated_at)
        VALUES(1, 50, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """
    )


def ensure_runtime_schema_ready(conn: Any) -> None:
    required_tables = (
        "users",
        "coupon_codes",
        "credit_ledger",
        "public_invite_claims",
        "public_invite_settings",
    )
    missing = [table_name for table_name in required_tables if not _table_exists(conn, table_name)]
    if missing:
        raise RuntimeError(
            "Business schema is missing required tables in Turso: " + ", ".join(sorted(missing))
        )


def init_db() -> None:
    from .user_identity import ensure_user_identity_schema

    with get_conn() as conn:
        if is_turso_enabled():
            ensure_runtime_schema_ready(conn)
            return
        ensure_current_schema(conn)
        ensure_user_identity_schema(conn)
        conn.commit()
