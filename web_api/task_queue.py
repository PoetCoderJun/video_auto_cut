from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_settings
from .constants import (
    TASK_STATUS_FAILED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
    TASK_TYPE_STEP1,
    TASK_TYPE_STEP2,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _queue_db_path() -> Path:
    settings = get_settings()
    return settings.work_dir / "local_task_queue.db"


def get_queue_db_path() -> Path:
    """Expose for logging/diagnostics."""
    return _queue_db_path()


def _connect() -> sqlite3.Connection:
    path = _queue_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_task_queue_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS queue_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                worker_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_task_id
            ON queue_tasks(status, task_id ASC);

            CREATE INDEX IF NOT EXISTS idx_queue_tasks_job_type_status
            ON queue_tasks(job_id, task_type, status, task_id DESC);
            """
        )
        conn.commit()


def _row_get(row: Any, key: str, index: int) -> Any:
    if row is None:
        return None
    if isinstance(row, (tuple, list)):
        if 0 <= index < len(row):
            return row[index]
        return None
    try:
        return row[key]
    except Exception:
        return None


def _task_row_to_dict(row: Any) -> dict[str, Any]:
    payload_json = _row_get(row, "payload_json", 4)
    try:
        payload = json.loads(str(payload_json or "{}"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    return {
        "task_id": int(_row_get(row, "task_id", 0)),
        "job_id": str(_row_get(row, "job_id", 1)),
        "task_type": str(_row_get(row, "task_type", 2)),
        "status": str(_row_get(row, "status", 3)),
        "payload": payload,
        "error_message": _row_get(row, "error_message", 5),
        "worker_id": _row_get(row, "worker_id", 6),
        "created_at": _row_get(row, "created_at", 7),
        "updated_at": _row_get(row, "updated_at", 8),
        "started_at": _row_get(row, "started_at", 9),
        "finished_at": _row_get(row, "finished_at", 10),
    }


def enqueue_task(job_id: str, task_type: str, payload: dict[str, Any] | None = None) -> int:
    if task_type not in {TASK_TYPE_STEP1, TASK_TYPE_STEP2}:
        raise RuntimeError(f"unsupported task type: {task_type}")

    now = _now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT task_id
            FROM queue_tasks
            WHERE job_id = ?
              AND task_type = ?
              AND status IN (?, ?)
            ORDER BY task_id DESC
            LIMIT 1
            """,
            (job_id, task_type, TASK_STATUS_QUEUED, TASK_STATUS_RUNNING),
        ).fetchone()
        if existing:
            task_id = int(_row_get(existing, "task_id", 0) or 0)
            conn.commit()
            if task_id > 0:
                return task_id

        cursor = conn.execute(
            """
            INSERT INTO queue_tasks(
                job_id,
                task_type,
                status,
                payload_json,
                error_message,
                worker_id,
                created_at,
                updated_at,
                started_at,
                finished_at
            )
            VALUES(?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
            """,
            (job_id, task_type, TASK_STATUS_QUEUED, payload_json, now, now),
        )
        task_id = int(getattr(cursor, "lastrowid", 0) or 0)
        if task_id <= 0:
            fallback = conn.execute(
                """
                SELECT task_id
                FROM queue_tasks
                WHERE job_id = ?
                  AND task_type = ?
                ORDER BY task_id DESC
                LIMIT 1
                """,
                (job_id, task_type),
            ).fetchone()
            task_id = int(_row_get(fallback, "task_id", 0) or 0)
        conn.commit()

    if task_id <= 0:
        raise RuntimeError("failed to enqueue task")
    return task_id


def claim_next_task() -> dict[str, Any] | None:
    worker_id = f"pid-{os.getpid()}"
    now = _now_iso()
    with _connect() as conn:
        for _ in range(3):
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT
                    task_id,
                    job_id,
                    task_type,
                    status,
                    payload_json,
                    error_message,
                    worker_id,
                    created_at,
                    updated_at,
                    started_at,
                    finished_at
                FROM queue_tasks
                WHERE status = ?
                ORDER BY task_id ASC
                LIMIT 1
                """,
                (TASK_STATUS_QUEUED,),
            ).fetchone()
            if not row:
                conn.commit()
                return None

            task_id = int(_row_get(row, "task_id", 0) or 0)
            if task_id <= 0:
                conn.rollback()
                continue

            updated = conn.execute(
                """
                UPDATE queue_tasks
                SET status = ?,
                    worker_id = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    error_message = NULL
                WHERE task_id = ?
                  AND status = ?
                """,
                (TASK_STATUS_RUNNING, worker_id, now, now, task_id, TASK_STATUS_QUEUED),
            )
            if int(getattr(updated, "rowcount", 0) or 0) <= 0:
                conn.rollback()
                continue

            claimed = conn.execute(
                """
                SELECT
                    task_id,
                    job_id,
                    task_type,
                    status,
                    payload_json,
                    error_message,
                    worker_id,
                    created_at,
                    updated_at,
                    started_at,
                    finished_at
                FROM queue_tasks
                WHERE task_id = ?
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            conn.commit()
            if claimed and str(_row_get(claimed, "status", 3)) == TASK_STATUS_RUNNING:
                return _task_row_to_dict(claimed)
    return None


def set_task_succeeded(task_id: int) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE queue_tasks
            SET status = ?,
                finished_at = ?,
                updated_at = ?,
                error_message = NULL
            WHERE task_id = ?
            """,
            (TASK_STATUS_SUCCEEDED, now, now, int(task_id)),
        )
        conn.commit()


def set_task_failed(task_id: int, error_message: str) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE queue_tasks
            SET status = ?,
                finished_at = ?,
                updated_at = ?,
                error_message = ?
            WHERE task_id = ?
            """,
            (TASK_STATUS_FAILED, now, now, str(error_message or ""), int(task_id)),
        )
        conn.commit()
