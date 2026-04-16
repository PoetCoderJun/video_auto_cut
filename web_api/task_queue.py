from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import get_settings
from .constants import (
    TASK_STATUS_FAILED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
    TASK_TYPE_TEST,
)
from .db import get_conn, is_local_only_mode, is_turso_enabled, retry_turso_operation
from .utils.persistence_helpers import now_iso, parse_iso_datetime, row_get


def get_queue_db_path() -> str:
    settings = get_settings()
    if is_turso_enabled():
        return f"shared-db:{settings.turso_local_replica_path}"
    return str(settings.turso_local_replica_path)


@retry_turso_operation("init task queue")
def init_task_queue_db() -> None:
    with get_conn() as conn:
        conn.execute(
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
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_task_id
            ON queue_tasks(status, task_id ASC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_queue_tasks_job_type_status
            ON queue_tasks(job_id, task_type, status, task_id DESC)
            """
        )
        conn.commit()
def _task_row_to_dict(row: Any) -> dict[str, Any]:
    payload_json = row_get(row, "payload_json", 4)
    try:
        payload = json.loads(str(payload_json or "{}"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    return {
        "task_id": int(row_get(row, "task_id", 0)),
        "job_id": str(row_get(row, "job_id", 1)),
        "task_type": str(row_get(row, "task_type", 2)),
        "status": str(row_get(row, "status", 3)),
        "payload": payload,
        "error_message": row_get(row, "error_message", 5),
        "worker_id": row_get(row, "worker_id", 6),
        "created_at": row_get(row, "created_at", 7),
        "updated_at": row_get(row, "updated_at", 8),
        "started_at": row_get(row, "started_at", 9),
        "finished_at": row_get(row, "finished_at", 10),
    }


@retry_turso_operation("reclaim stale queue tasks")
def reclaim_stale_running_tasks(*, now: datetime | None = None) -> int:
    settings = get_settings()
    lease_seconds = float(settings.task_queue_lease_seconds)
    if lease_seconds <= 0:
        return 0

    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    cutoff = now_utc - timedelta(seconds=lease_seconds)
    reclaimed = 0

    with get_conn() as conn:
        stale_rows = conn.execute(
            """
            SELECT task_id, updated_at
            FROM queue_tasks
            WHERE status = ?
            ORDER BY task_id ASC
            """,
            (TASK_STATUS_RUNNING,),
        ).fetchall()

        stale_task_ids: list[int] = []
        for row in stale_rows:
            task_id = int(row_get(row, "task_id", 0) or 0)
            updated_at = parse_iso_datetime(row_get(row, "updated_at", 8))
            if task_id <= 0:
                continue
            if updated_at is None or updated_at < cutoff:
                stale_task_ids.append(task_id)

        for task_id in stale_task_ids:
            updated = conn.execute(
                """
                UPDATE queue_tasks
                SET status = ?,
                    worker_id = NULL,
                    error_message = CASE
                        WHEN error_message IS NULL OR TRIM(error_message) = ''
                        THEN 'TASK_HEARTBEAT_TIMEOUT'
                        ELSE error_message
                    END,
                    updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (TASK_STATUS_QUEUED, now_iso(), task_id, TASK_STATUS_RUNNING),
            )
            if int(getattr(updated, "rowcount", 0) or 0) > 0:
                reclaimed += 1
        conn.commit()

    return reclaimed


@retry_turso_operation("heartbeat task")
def heartbeat_task(task_id: int, *, worker_id: str) -> bool:
    now = now_iso()
    with get_conn() as conn:
        updated = conn.execute(
            """
            UPDATE queue_tasks
            SET updated_at = ?,
                error_message = CASE
                    WHEN error_message IS NULL OR error_message = 'TASK_HEARTBEAT_TIMEOUT'
                    THEN NULL
                    ELSE error_message
                END
            WHERE task_id = ?
              AND status = ?
              AND worker_id = ?
            """,
            (now, int(task_id), TASK_STATUS_RUNNING, str(worker_id)),
        )
        conn.commit()
    return int(getattr(updated, "rowcount", 0) or 0) > 0


@retry_turso_operation("enqueue task")
def enqueue_task(job_id: str, task_type: str, payload: dict[str, Any] | None = None) -> int:
    if task_type != TASK_TYPE_TEST:
        raise RuntimeError(f"unsupported task type: {task_type}")

    now = now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with get_conn() as conn:
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
            task_id = int(row_get(existing, "task_id", 0) or 0)
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
            task_id = int(row_get(fallback, "task_id", 0) or 0)
        conn.commit()

    if task_id <= 0:
        raise RuntimeError("failed to enqueue task")
    return task_id


def claim_next_task() -> dict[str, Any] | None:
    # Claiming changes task ownership. Let the worker loop retry on failure
    # instead of replaying the claim inside this function.
    worker_id = f"pid-{os.getpid()}"
    now = now_iso()
    reclaim_stale_running_tasks(now=datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone(timezone.utc))
    with get_conn() as conn:
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

            task_id = int(row_get(row, "task_id", 0) or 0)
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
            if claimed and str(row_get(claimed, "status", 3)) == TASK_STATUS_RUNNING:
                return _task_row_to_dict(claimed)
    return None


@retry_turso_operation("mark task succeeded")
def set_task_succeeded(task_id: int) -> None:
    now = now_iso()
    with get_conn() as conn:
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


@retry_turso_operation("mark task failed")
def set_task_failed(task_id: int, error_message: str) -> None:
    now = now_iso()
    with get_conn() as conn:
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
