from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .constants import (
    JOB_STATUS_SUCCEEDED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
    TASK_STATUS_FAILED,
)
from .db import get_conn


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_job(job_id: str, status: str) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs(job_id, status, progress, error_code, error_message, created_at, updated_at)
            VALUES(?, ?, 0, NULL, NULL, ?, ?)
            """,
            (job_id, status, now, now),
        )
        conn.execute(
            """
            INSERT INTO job_files(
                job_id, video_path, srt_path, optimized_srt_path, final_step1_srt_path,
                topics_path, final_topics_path, final_video_path, updated_at
            ) VALUES(?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)
            """,
            (job_id, now),
        )
        conn.commit()
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "progress": int(row["progress"]),
        "error": (
            None
            if not row["error_code"]
            else {"code": row["error_code"], "message": row["error_message"] or ""}
        ),
    }


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    now = now_iso()
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [now]

    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if progress is not None:
        fields.append("progress = ?")
        values.append(int(progress))

    if error_code is None and error_message is None:
        fields.append("error_code = NULL")
        fields.append("error_message = NULL")
    else:
        fields.append("error_code = ?")
        fields.append("error_message = ?")
        values.append(error_code)
        values.append(error_message)

    values.append(job_id)
    query = f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?"

    with get_conn() as conn:
        conn.execute(query, tuple(values))
        conn.commit()


def get_job_files(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM job_files WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def upsert_job_files(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    now = now_iso()
    allowed = {
        "video_path",
        "srt_path",
        "optimized_srt_path",
        "final_step1_srt_path",
        "topics_path",
        "final_topics_path",
        "final_video_path",
    }
    fields = [key for key in kwargs if key in allowed]
    if not fields:
        return

    set_clause = ", ".join([f"{name} = ?" for name in fields] + ["updated_at = ?"])
    values = [kwargs[name] for name in fields] + [now, job_id]

    with get_conn() as conn:
        conn.execute(f"UPDATE job_files SET {set_clause} WHERE job_id = ?", tuple(values))
        conn.commit()


def clear_step_data(job_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM job_step1_lines WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_step2_chapters WHERE job_id = ?", (job_id,))
        conn.commit()


def list_expired_succeeded_jobs(cutoff_updated_at: str, *, limit: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT j.job_id
            FROM jobs j
            JOIN job_files f ON f.job_id = j.job_id
            WHERE j.status = ?
              AND j.updated_at <= ?
              AND (
                f.video_path IS NOT NULL
                OR f.srt_path IS NOT NULL
                OR f.optimized_srt_path IS NOT NULL
                OR f.final_step1_srt_path IS NOT NULL
                OR f.topics_path IS NOT NULL
                OR f.final_topics_path IS NOT NULL
                OR f.final_video_path IS NOT NULL
              )
            ORDER BY j.updated_at ASC
            LIMIT ?
            """,
            (JOB_STATUS_SUCCEEDED, cutoff_updated_at, int(limit)),
        ).fetchall()
    return [str(row["job_id"]) for row in rows]


def replace_step1_lines(job_id: str, lines: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM job_step1_lines WHERE job_id = ?", (job_id,))
        conn.executemany(
            """
            INSERT INTO job_step1_lines(
                job_id, line_id, start_sec, end_sec, original_text, optimized_text,
                ai_suggest_remove, user_final_remove
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    job_id,
                    int(line["line_id"]),
                    float(line["start"]),
                    float(line["end"]),
                    str(line["original_text"]),
                    str(line["optimized_text"]),
                    1 if bool(line["ai_suggest_remove"]) else 0,
                    1 if bool(line["user_final_remove"]) else 0,
                )
                for line in lines
            ],
        )
        conn.commit()


def list_step1_lines(job_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_step1_lines WHERE job_id = ? ORDER BY line_id ASC", (job_id,)
        ).fetchall()
    return [
        {
            "line_id": int(row["line_id"]),
            "start": float(row["start_sec"]),
            "end": float(row["end_sec"]),
            "original_text": row["original_text"],
            "optimized_text": row["optimized_text"],
            "ai_suggest_remove": bool(row["ai_suggest_remove"]),
            "user_final_remove": bool(row["user_final_remove"]),
        }
        for row in rows
    ]


def replace_step2_chapters(job_id: str, chapters: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM job_step2_chapters WHERE job_id = ?", (job_id,))
        conn.executemany(
            """
            INSERT INTO job_step2_chapters(
                job_id, chapter_id, title, summary, start_sec, end_sec, line_ids_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    job_id,
                    int(chapter["chapter_id"]),
                    str(chapter.get("title", "")).strip() or f"章节{int(chapter['chapter_id'])}",
                    str(chapter.get("summary", "")).strip(),
                    float(chapter["start"]),
                    float(chapter["end"]),
                    json.dumps(chapter.get("line_ids", []), ensure_ascii=False),
                )
                for chapter in chapters
            ],
        )
        conn.commit()


def list_step2_chapters(job_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_step2_chapters WHERE job_id = ? ORDER BY chapter_id ASC", (job_id,)
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            line_ids = json.loads(row["line_ids_json"] or "[]")
        except json.JSONDecodeError:
            line_ids = []
        result.append(
            {
                "chapter_id": int(row["chapter_id"]),
                "title": row["title"],
                "summary": row["summary"],
                "start": float(row["start_sec"]),
                "end": float(row["end_sec"]),
                "line_ids": line_ids if isinstance(line_ids, list) else [],
            }
        )
    return result


def has_pending_task(job_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(1) AS c
            FROM job_tasks
            WHERE job_id = ? AND status IN (?, ?)
            """,
            (job_id, TASK_STATUS_QUEUED, TASK_STATUS_RUNNING),
        ).fetchone()
    return bool(row and int(row["c"]) > 0)


def enqueue_task(job_id: str, task_type: str, payload: dict[str, Any] | None = None) -> int:
    now = now_iso()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO job_tasks(job_id, task_type, payload_json, status, error_message, created_at, updated_at)
            VALUES(?, ?, ?, ?, NULL, ?, ?)
            """,
            (job_id, task_type, payload_json, TASK_STATUS_QUEUED, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def claim_next_task() -> dict[str, Any] | None:
    now = now_iso()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM job_tasks
            WHERE status = ?
            ORDER BY task_id ASC
            LIMIT 1
            """,
            (TASK_STATUS_QUEUED,),
        ).fetchone()
        if not row:
            conn.commit()
            return None

        conn.execute(
            "UPDATE job_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (TASK_STATUS_RUNNING, now, int(row["task_id"])),
        )
        conn.commit()

    payload: dict[str, Any]
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "task_id": int(row["task_id"]),
        "job_id": row["job_id"],
        "task_type": row["task_type"],
        "payload": payload,
    }


def set_task_succeeded(task_id: int) -> None:
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE job_tasks SET status = ?, error_message = NULL, updated_at = ? WHERE task_id = ?",
            (TASK_STATUS_SUCCEEDED, now, task_id),
        )
        conn.commit()


def set_task_failed(task_id: int, error_message: str) -> None:
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            "UPDATE job_tasks SET status = ?, error_message = ?, updated_at = ? WHERE task_id = ?",
            (TASK_STATUS_FAILED, error_message, now, task_id),
        )
        conn.commit()
