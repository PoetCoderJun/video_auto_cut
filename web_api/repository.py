from __future__ import annotations

import hashlib
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
from .services.code_sheet import SheetCode, get_sheet_code

USER_STATUS_PENDING_INVITE = "PENDING_INVITE"
USER_STATUS_ACTIVE = "ACTIVE"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_user(user_id: str, email: str | None) -> None:
    now = now_iso()
    normalized_email = (email or "").strip().lower() or None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, email, status, invite_activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, invite_activated_at, created_at, updated_at)
                VALUES(?, ?, ?, NULL, ?, ?)
                """,
                (user_id, normalized_email, USER_STATUS_PENDING_INVITE, now, now),
            )
            conn.commit()
            return

        if normalized_email is None:
            return

        previous_email = row["email"]
        if previous_email != normalized_email:
            conn.execute(
                "UPDATE users SET email = ?, updated_at = ? WHERE user_id = ?",
                (normalized_email, now, user_id),
            )
            conn.commit()


def get_user(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, email, status, invite_activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "user_id": str(row["user_id"]),
        "email": row["email"],
        "status": row["status"] or USER_STATUS_PENDING_INVITE,
        "invite_activated_at": row["invite_activated_at"],
    }


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def get_credit_balance(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT balance FROM credit_wallets WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return 0
    return int(row["balance"])


def get_recent_credit_ledger(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT entry_id, delta, reason, job_id, idempotency_key, created_at
            FROM credit_ledger
            WHERE user_id = ?
            ORDER BY entry_id DESC
            LIMIT ?
            """,
            (user_id, int(max(1, limit))),
        ).fetchall()
    return [
        {
            "entry_id": int(row["entry_id"]),
            "delta": int(row["delta"]),
            "reason": str(row["reason"]),
            "job_id": row["job_id"],
            "idempotency_key": str(row["idempotency_key"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def redeem_coupon_code(user_id: str, code: str) -> dict[str, Any]:
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("coupon code cannot be empty")
    now = now_iso()
    sheet_code = get_sheet_code(normalized)
    if sheet_code is None:
        raise LookupError("COUPON_CODE_INVALID")

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            "SELECT user_id, status, invite_activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, invite_activated_at, created_at, updated_at)
                VALUES(?, NULL, ?, NULL, ?, ?)
                """,
                (user_id, USER_STATUS_PENDING_INVITE, now, now),
            )
        else:
            user_status = str(user["status"] or "").upper()
            if user_status == USER_STATUS_ACTIVE or user["invite_activated_at"]:
                balance = _get_balance_in_tx(conn, user_id)
                conn.commit()
                return {
                    "already_activated": True,
                    "coupon_redeemed": True,
                    "granted_credits": 0,
                    "balance": balance,
                }

        try:
            _assert_sheet_code_usable_in_tx(conn, sheet_code)
        except LookupError:
            conn.rollback()
            raise

        conn.execute(
            """
            INSERT OR IGNORE INTO activation_code_redemptions(code, user_id, credits, redeemed_at)
            VALUES(?, ?, ?, ?)
            """,
            (sheet_code.code, user_id, int(sheet_code.credits), now),
        )
        _activate_user_in_tx(conn, user_id, now)
        granted = _grant_credits_in_tx(
            conn,
            user_id,
            int(sheet_code.credits),
            reason="COUPON_REDEEM",
            job_id=None,
            idempotency_key=f"sheetcode:{sheet_code.code}:user:{user_id}",
            created_at=now,
        )
        balance = _get_balance_in_tx(conn, user_id)
        conn.commit()
        return {
            "already_activated": False,
            "coupon_redeemed": True,
            "granted_credits": granted,
            "balance": balance,
        }


def _assert_not_expired_or_invalid(expires_at: Any) -> None:
    if not isinstance(expires_at, str) or not expires_at.strip():
        return
    try:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        if expires_dt < now_dt:
            raise LookupError("COUPON_CODE_EXPIRED")
    except LookupError:
        raise
    except Exception:
        # invalid expires_at format should fail closed for safety.
        raise LookupError("COUPON_CODE_INVALID")


def _activate_user_in_tx(conn: Any, user_id: str, now: str) -> None:
    conn.execute(
        """
        UPDATE users
        SET status = ?, invite_activated_at = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (USER_STATUS_ACTIVE, now, now, user_id),
    )


def _assert_sheet_code_usable_in_tx(conn: Any, sheet_code: SheetCode) -> None:
    status = str(sheet_code.status or "").upper()
    if status != "ACTIVE":
        raise LookupError("COUPON_CODE_INVALID")

    _assert_not_expired_or_invalid(sheet_code.expires_at)

    max_uses = sheet_code.max_uses
    if max_uses is None:
        return
    row = conn.execute(
        "SELECT COUNT(1) AS c FROM activation_code_redemptions WHERE code = ?",
        (sheet_code.code,),
    ).fetchone()
    used_count = int(row["c"]) if row else 0
    if used_count >= int(max_uses):
        raise LookupError("COUPON_CODE_EXHAUSTED")


def _get_balance_in_tx(conn: Any, user_id: str) -> int:
    row = conn.execute("SELECT balance FROM credit_wallets WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["balance"]) if row else 0


def _grant_credits_in_tx(
    conn: Any,
    user_id: str,
    delta: int,
    *,
    reason: str,
    job_id: str | None,
    idempotency_key: str,
    created_at: str,
) -> int:
    if delta <= 0:
        raise ValueError("delta must be > 0")
    existing = conn.execute(
        "SELECT delta FROM credit_ledger WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing:
        return 0

    conn.execute(
        "INSERT OR IGNORE INTO credit_wallets(user_id, balance, updated_at) VALUES(?, 0, ?)",
        (user_id, created_at),
    )
    conn.execute(
        "UPDATE credit_wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
        (int(delta), created_at, user_id),
    )
    conn.execute(
        """
        INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (user_id, int(delta), reason, job_id, idempotency_key, created_at),
    )
    return int(delta)


def create_job(job_id: str, status: str, owner_user_id: str) -> dict[str, Any]:
    now = now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs(job_id, owner_user_id, status, progress, error_code, error_message, created_at, updated_at)
            VALUES(?, ?, ?, 0, NULL, NULL, ?, ?)
            """,
            (job_id, owner_user_id, status, now, now),
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
    return get_job(job_id, owner_user_id=owner_user_id)


def get_job(job_id: str, *, owner_user_id: str | None = None) -> dict[str, Any] | None:
    with get_conn() as conn:
        if owner_user_id:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ? AND owner_user_id = ?",
                (job_id, owner_user_id),
            ).fetchone()
        else:
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


def touch_job(job_id: str) -> None:
    now = now_iso()
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET updated_at = ? WHERE job_id = ?", (now, job_id))
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


def list_succeeded_jobs_with_artifacts(*, limit: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT j.job_id
            FROM jobs j
            JOIN job_files f ON f.job_id = j.job_id
            WHERE j.status = ?
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
            (JOB_STATUS_SUCCEEDED, int(limit)),
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
