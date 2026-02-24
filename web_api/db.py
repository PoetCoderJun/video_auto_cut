from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import get_settings

try:
    import libsql  # type: ignore
except Exception:  # pragma: no cover - optional dependency for Turso mode
    libsql = None


def _is_turso_enabled() -> bool:
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
        if hasattr(row, "keys"):
            try:
                value = row["name"]  # type: ignore[index]
                columns.add(str(value))
                continue
            except Exception:
                pass
        try:
            # PRAGMA table_info format: (cid, name, type, notnull, dflt_value, pk)
            columns.add(str(row[1]))
            continue
        except Exception:
            logging.debug("[web_api] failed to parse PRAGMA table_info row: %r", row)
    return columns


def _create_conn() -> Any:
    settings = get_settings()
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
        # Some libsql builds may not expose row_factory assignment.
        pass
    if hasattr(conn, "sync"):
        conn.sync()
    return conn


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
            conn.sync()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        _executescript(
            conn,
            f"""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                owner_user_id TEXT,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING_INVITE',
                invite_activated_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_files (
                job_id TEXT PRIMARY KEY,
                video_path TEXT,
                srt_path TEXT,
                optimized_srt_path TEXT,
                final_step1_srt_path TEXT,
                topics_path TEXT,
                final_topics_path TEXT,
                final_video_path TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_step1_lines (
                job_id TEXT NOT NULL,
                line_id INTEGER NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                original_text TEXT NOT NULL,
                optimized_text TEXT NOT NULL,
                ai_suggest_remove INTEGER NOT NULL,
                user_final_remove INTEGER NOT NULL,
                PRIMARY KEY(job_id, line_id),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_step2_chapters (
                job_id TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                start_sec REAL NOT NULL,
                end_sec REAL NOT NULL,
                line_ids_json TEXT NOT NULL,
                PRIMARY KEY(job_id, chapter_id),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS job_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS credit_wallets (
                user_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS activation_code_redemptions (
                redemption_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id TEXT NOT NULL,
                credits INTEGER NOT NULL,
                redeemed_at TEXT NOT NULL,
                UNIQUE(code, user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_job_tasks_status ON job_tasks(status, task_id);
            CREATE INDEX IF NOT EXISTS idx_job_tasks_job_id ON job_tasks(job_id, status);
            CREATE INDEX IF NOT EXISTS idx_credit_ledger_user_created_at ON credit_ledger(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_owner_updated ON jobs(owner_user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_activation_code_redemptions_code ON activation_code_redemptions(code);
            """
        )
        rows = conn.execute("PRAGMA table_info(jobs)").fetchall()
        columns = _extract_column_names(list(rows))
        if columns and "owner_user_id" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN owner_user_id TEXT")

        rows = conn.execute("PRAGMA table_info(users)").fetchall()
        columns = _extract_column_names(list(rows))
        if columns and "status" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING_INVITE'")
        if columns and "invite_activated_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN invite_activated_at TEXT")

        conn.commit()
