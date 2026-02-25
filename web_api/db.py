from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import get_settings

try:
    import libsql  # type: ignore
except Exception:  # pragma: no cover - optional dependency for Turso mode
    libsql = None


def _is_local_only_mode() -> bool:
    raw = (os.getenv("WEB_DB_LOCAL_ONLY") or "").strip().lower()
    return raw in {"1", "true", "yes"}


def _is_turso_enabled() -> bool:
    if _is_local_only_mode():
        return False
    settings = get_settings()
    return bool(settings.turso_database_url and settings.turso_auth_token)


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


def _create_conn() -> Any:
    settings = get_settings()
    if _is_local_only_mode():
        return _create_local_conn()

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

    try:
        conn = libsql.connect(str(settings.turso_local_replica_path), **connect_kwargs)
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        _sync_best_effort(conn, stage="open")
        return conn
    except Exception as exc:
        logging.warning("[web_api] turso connect failed, fallback to local replica sqlite: %s", exc)
        return _create_local_conn()


def _sync_best_effort(conn: Any, *, stage: str) -> None:
    if not hasattr(conn, "sync"):
        return
    try:
        conn.sync()
    except Exception as exc:
        logging.warning("[web_api] turso sync failed at %s: %s", stage, exc)


def _executescript(conn: Any, script: str) -> None:
    if hasattr(conn, "executescript"):
        conn.executescript(script)
        return
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


def init_db() -> None:
    with get_conn() as conn:
        _executescript(
            conn,
            """
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

            CREATE INDEX IF NOT EXISTS idx_coupon_codes_status_created_at
            ON coupon_codes(status, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_coupon_codes_source
            ON coupon_codes(source);

            CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created_at
            ON credit_ledger(user_id, created_at DESC);
            """,
        )

        user_columns = _extract_column_names(list(conn.execute("PRAGMA table_info(users)").fetchall()))
        if user_columns and "status" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING_COUPON'")
        if user_columns and "activated_at" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN activated_at TEXT")
        if user_columns and "invite_activated_at" in user_columns:
            conn.execute(
                """
                UPDATE users
                SET activated_at = COALESCE(activated_at, invite_activated_at)
                WHERE activated_at IS NULL AND invite_activated_at IS NOT NULL
                """
            )
        conn.execute(
            """
            UPDATE users
            SET status = 'PENDING_COUPON'
            WHERE status IN ('PENDING_INVITE', 'PENDING_ACTIVATION')
            """
        )

        coupon_columns = _extract_column_names(list(conn.execute("PRAGMA table_info(coupon_codes)").fetchall()))
        if coupon_columns and "max_uses" in coupon_columns:
            conn.execute("DROP TABLE IF EXISTS coupon_codes_v2")
            conn.execute(
                """
                CREATE TABLE coupon_codes_v2 (
                    coupon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    credits INTEGER NOT NULL,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT,
                    status TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO coupon_codes_v2(
                    coupon_id,
                    code,
                    credits,
                    used_count,
                    expires_at,
                    status,
                    source,
                    created_at,
                    updated_at
                )
                SELECT
                    coupon_id,
                    code,
                    credits,
                    CASE WHEN COALESCE(used_count, 0) >= 1 THEN 1 ELSE 0 END,
                    expires_at,
                    COALESCE(status, 'ACTIVE'),
                    source,
                    COALESCE(created_at, updated_at, '1970-01-01T00:00:00Z'),
                    COALESCE(updated_at, created_at, '1970-01-01T00:00:00Z')
                FROM coupon_codes
                """
            )
            conn.execute("DROP TABLE coupon_codes")
            conn.execute("ALTER TABLE coupon_codes_v2 RENAME TO coupon_codes")

        if _table_exists(conn, "coupons"):
            coupon_columns = _extract_column_names(list(conn.execute("PRAGMA table_info(coupons)").fetchall()))
            if "code_plain" in coupon_columns:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO coupon_codes(
                        code,
                        credits,
                        used_count,
                        expires_at,
                        status,
                        source,
                        created_at,
                        updated_at
                    )
                    SELECT
                        code_plain,
                        credits,
                        CASE WHEN COALESCE(redeemed_count, 0) >= 1 THEN 1 ELSE 0 END,
                        expires_at,
                        CASE WHEN COALESCE(redeemed_count, 0) >= 1 THEN 'DISABLED' ELSE COALESCE(status, 'ACTIVE') END,
                        source_user_id,
                        created_at,
                        updated_at
                    FROM coupons
                    WHERE code_plain IS NOT NULL AND TRIM(code_plain) <> ''
                    """
                )

        if _table_exists(conn, "coupon_redemptions"):
            redemption_columns = _extract_column_names(
                list(conn.execute("PRAGMA table_info(coupon_redemptions)").fetchall())
            )
            if {"coupon_code", "user_id", "credits", "redeemed_at"}.issubset(redemption_columns):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                    SELECT
                        user_id,
                        credits,
                        'COUPON_REDEEM',
                        NULL,
                        'coupon:' || coupon_code || ':legacy:' || user_id,
                        redeemed_at
                    FROM coupon_redemptions
                    """
                )

        if _table_exists(conn, "activation_code_redemptions"):
            legacy_columns = _extract_column_names(
                list(conn.execute("PRAGMA table_info(activation_code_redemptions)").fetchall())
            )
            if {"code", "user_id", "credits", "redeemed_at"}.issubset(legacy_columns):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                    SELECT
                        user_id,
                        credits,
                        'COUPON_REDEEM',
                        NULL,
                        'coupon:' || code || ':legacy:' || user_id,
                        redeemed_at
                    FROM activation_code_redemptions
                    """
                )

        conn.execute(
            """
            UPDATE coupon_codes
            SET used_count = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM credit_ledger l
                    WHERE l.reason = 'COUPON_REDEEM'
                      AND (
                        l.idempotency_key = 'coupon:' || coupon_codes.code
                        OR l.idempotency_key LIKE 'coupon:' || coupon_codes.code || ':legacy:%'
                      )
                ) THEN 1
                ELSE 0
            END
            """
        )

        conn.execute(
            """
            UPDATE coupon_codes
            SET status = 'DISABLED'
            WHERE used_count >= 1
            """
        )

        conn.execute(
            """
            UPDATE coupon_codes
            SET status = 'ACTIVE'
            WHERE status IS NULL OR TRIM(status) = ''
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_coupon_codes_status_created_at ON coupon_codes(status, created_at DESC)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_coupon_codes_source ON coupon_codes(source)")

        # Shrink Turso schema to business-only tables for MVP.
        for table_name in (
            "job_tasks",
            "jobs",
            "job_files",
            "job_step1_lines",
            "job_step2_chapters",
            "credit_wallets",
            "coupon_redemptions",
            "invite_codes",
            "invite_claims",
            "coupons",
            "activation_code_redemptions",
        ):
            if _table_exists(conn, table_name):
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")

        conn.commit()
