from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ensure_job_dirs, get_settings, job_dir
from .constants import (
    ALLOWED_VIDEO_EXTENSIONS,
    JOB_STATUS_CREATED,
    JOB_STATUS_FAILED,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP1_RUNNING,
    JOB_STATUS_STEP1_READY,
    JOB_STATUS_STEP2_CONFIRMED,
    JOB_STATUS_STEP2_RUNNING,
    JOB_STATUS_STEP2_READY,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_UPLOAD_READY,
)
from .db import get_conn

USER_STATUS_PENDING_COUPON = "PENDING_COUPON"
USER_STATUS_ACTIVE = "ACTIVE"

JOB_FILE_FIELDS = (
    "video_path",
    "audio_path",
    "srt_path",
    "optimized_srt_path",
    "final_step1_srt_path",
    "topics_path",
    "final_topics_path",
    "final_video_path",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_user(user_id: str, email: str | None) -> None:
    now = now_iso()
    normalized_email = (email or "").strip().lower() or None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, email, status, activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
                VALUES(?, ?, ?, NULL, ?, ?)
                """,
                (user_id, normalized_email, USER_STATUS_PENDING_COUPON, now, now),
            )
            conn.commit()
            return

        if normalized_email is None:
            return

        previous_email = _row_get(row, "email", 1)
        if previous_email != normalized_email:
            conn.execute(
                "UPDATE users SET email = ?, updated_at = ? WHERE user_id = ?",
                (normalized_email, now, user_id),
            )
            conn.commit()


def get_user(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, email, status, activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "user_id": str(_row_get(row, "user_id", 0)),
        "email": _row_get(row, "email", 1),
        "status": _row_get(row, "status", 2) or USER_STATUS_PENDING_COUPON,
        "activated_at": _row_get(row, "activated_at", 3),
    }


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def get_credit_balance(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    return int(_row_get(row, "balance", 0) or 0)


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
            "entry_id": int(_row_get(row, "entry_id", 0)),
            "delta": int(_row_get(row, "delta", 1)),
            "reason": str(_row_get(row, "reason", 2)),
            "job_id": _row_get(row, "job_id", 3),
            "idempotency_key": str(_row_get(row, "idempotency_key", 4)),
            "created_at": str(_row_get(row, "created_at", 5)),
        }
        for row in rows
    ]


def consume_step1_credit(user_id: str, job_id: str) -> dict[str, Any]:
    idempotency_key = f"job:{job_id}:step1_success"
    now = now_iso()

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")

        existing = conn.execute(
            "SELECT entry_id FROM credit_ledger WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        if existing:
            balance = _get_balance_in_tx(conn, user_id)
            conn.commit()
            return {"consumed": False, "balance": balance}

        balance = _get_balance_in_tx(conn, user_id)
        if balance < 1:
            conn.rollback()
            raise LookupError("INSUFFICIENT_CREDITS")

        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
            VALUES(?, -1, 'JOB_STEP1_SUCCESS', ?, ?, ?)
            """,
            (user_id, job_id, idempotency_key, now),
        )
        if int(getattr(inserted, "rowcount", 0) or 0) <= 0:
            balance = _get_balance_in_tx(conn, user_id)
            conn.commit()
            return {"consumed": False, "balance": balance}

        balance = _get_balance_in_tx(conn, user_id)
        conn.commit()
        return {"consumed": True, "balance": balance}


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
        raise LookupError("COUPON_CODE_INVALID")


def _assert_coupon_usable_in_tx(coupon: Any) -> None:
    used_count = int(_row_get(coupon, "used_count", 2) or 0)
    if used_count >= 1:
        raise LookupError("COUPON_CODE_EXHAUSTED")

    status = str(_row_get(coupon, "status", 4) or "").upper()
    if status != "ACTIVE":
        raise LookupError("COUPON_CODE_INVALID")

    _assert_not_expired_or_invalid(_row_get(coupon, "expires_at", 3))


def preview_coupon_code(code: str) -> dict[str, Any]:
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("coupon code cannot be empty")

    with get_conn() as conn:
        coupon = conn.execute(
            """
            SELECT code, credits, used_count, expires_at, status
            FROM coupon_codes
            WHERE code = ?
            """,
            (normalized,),
        ).fetchone()
    if not coupon:
        raise LookupError("COUPON_CODE_INVALID")

    _assert_coupon_usable_in_tx(coupon)
    credits = int(_row_get(coupon, "credits", 1) or 0)
    if credits <= 0:
        raise LookupError("COUPON_CODE_INVALID")
    return {"code": normalized, "credits": credits}


def _activate_user_in_tx(conn: Any, user_id: str, now: str) -> None:
    conn.execute(
        """
        UPDATE users
        SET status = ?, activated_at = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (USER_STATUS_ACTIVE, now, now, user_id),
    )


def redeem_coupon_code(user_id: str, code: str) -> dict[str, Any]:
    normalized = normalize_code(code)
    if not normalized:
        raise ValueError("coupon code cannot be empty")

    idempotency_key = f"coupon:{normalized}"
    now = now_iso()

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            "SELECT user_id, status, activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
                VALUES(?, NULL, ?, NULL, ?, ?)
                """,
                (user_id, USER_STATUS_PENDING_COUPON, now, now),
            )
            already_activated = False
        else:
            user_status = str(_row_get(user, "status", 1) or "").upper()
            already_activated = user_status == USER_STATUS_ACTIVE or bool(_row_get(user, "activated_at", 2))

        coupon = conn.execute(
            """
            SELECT code, credits, used_count, expires_at, status
            FROM coupon_codes
            WHERE code = ?
            """,
            (normalized,),
        ).fetchone()
        if not coupon:
            conn.rollback()
            raise LookupError("COUPON_CODE_INVALID")

        try:
            _assert_coupon_usable_in_tx(coupon)
        except LookupError:
            conn.rollback()
            raise

        credits = int(_row_get(coupon, "credits", 1) or 0)
        if credits <= 0:
            conn.rollback()
            raise LookupError("COUPON_CODE_INVALID")

        reserved = conn.execute(
            """
            UPDATE coupon_codes
            SET used_count = 1, status = 'DISABLED', updated_at = ?
            WHERE code = ? AND status = 'ACTIVE' AND COALESCE(used_count, 0) = 0
            """,
            (now, normalized),
        )
        if int(getattr(reserved, "rowcount", 0) or 0) <= 0:
            conn.rollback()
            raise LookupError("COUPON_CODE_EXHAUSTED")

        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
            VALUES(?, ?, 'COUPON_REDEEM', NULL, ?, ?)
            """,
            (user_id, credits, idempotency_key, now),
        )
        if int(getattr(inserted, "rowcount", 0) or 0) <= 0:
            conn.rollback()
            raise LookupError("COUPON_CODE_EXHAUSTED")

        _activate_user_in_tx(conn, user_id, now)
        balance = _get_balance_in_tx(conn, user_id)
        conn.commit()
        return {
            "already_activated": already_activated,
            "coupon_redeemed": True,
            "granted_credits": credits,
            "balance": balance,
        }


def _get_balance_in_tx(conn: Any, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(_row_get(row, "balance", 0) or 0)


def _meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.meta.json"


def _files_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.files.json"


def _error_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.error.json"


def _step1_confirmed_path(job_id: str) -> Path:
    return job_dir(job_id) / "step1" / ".confirmed"


def _step2_confirmed_path(job_id: str) -> Path:
    return job_dir(job_id) / "step2" / ".confirmed"


def _step1_lines_path(job_id: str) -> Path:
    return job_dir(job_id) / "step1" / "final_step1.json"


def _step2_topics_path(job_id: str) -> Path:
    return job_dir(job_id) / "step2" / "final_topics.json"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_meta(job_id: str) -> dict[str, Any] | None:
    meta = _read_json(_meta_path(job_id))
    if isinstance(meta, dict):
        return meta
    return None


def _read_files_manifest(job_id: str) -> dict[str, Any]:
    payload = _read_json(_files_path(job_id))
    if isinstance(payload, dict):
        return payload
    return {}


def _write_files_manifest(job_id: str, payload: dict[str, Any]) -> None:
    _write_json(_files_path(job_id), payload)


def _existing_video_path(job_id: str) -> str | None:
    input_dir = job_dir(job_id) / "input"
    if not input_dir.exists():
        return None
    files = [
        item
        for item in input_dir.iterdir()
        if item.is_file()
        and not item.name.startswith(".")
        and item.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS
    ]
    if not files:
        return None
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return str(files[0])

def _existing_audio_path(job_id: str) -> str | None:
    input_dir = job_dir(job_id) / "input"
    if not input_dir.exists():
        return None
    candidates = [item for item in input_dir.iterdir() if item.is_file() and item.name.startswith("audio.")]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return str(candidates[0])


def _normalize_files(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"job_id": job_id}
    for field in JOB_FILE_FIELDS:
        raw = payload.get(field)
        if isinstance(raw, str) and raw.strip() and Path(raw).exists():
            result[field] = raw
        else:
            result[field] = None

    # Fallbacks by conventional paths.
    if not result["video_path"]:
        result["video_path"] = _existing_video_path(job_id)
    if not result["audio_path"]:
        result["audio_path"] = _existing_audio_path(job_id)

    step1_srt = job_dir(job_id) / "step1" / "final_step1.srt"
    if step1_srt.exists():
        result["final_step1_srt_path"] = str(step1_srt)

    topics_path = job_dir(job_id) / "step2" / "topics.json"
    if topics_path.exists():
        result["topics_path"] = str(topics_path)

    final_topics = _step2_topics_path(job_id)
    if final_topics.exists():
        result["final_topics_path"] = str(final_topics)

    final_video = job_dir(job_id) / "render" / "output.mp4"
    if final_video.exists():
        result["final_video_path"] = str(final_video)

    return result


def _infer_job_status(job_id: str) -> str:
    files = _normalize_files(job_id, _read_files_manifest(job_id))
    if _error_path(job_id).exists():
        return JOB_STATUS_FAILED
    if files.get("final_video_path"):
        return JOB_STATUS_SUCCEEDED
    if _step2_confirmed_path(job_id).exists():
        return JOB_STATUS_STEP2_CONFIRMED
    if files.get("final_topics_path"):
        return JOB_STATUS_STEP2_READY
    if _step1_confirmed_path(job_id).exists():
        return JOB_STATUS_STEP1_CONFIRMED
    if _step1_lines_path(job_id).exists():
        return JOB_STATUS_STEP1_READY
    if files.get("video_path") or files.get("audio_path"):
        return JOB_STATUS_UPLOAD_READY
    return JOB_STATUS_CREATED


def _progress_for_status(status: str) -> int:
    mapping = {
        JOB_STATUS_CREATED: 0,
        JOB_STATUS_UPLOAD_READY: 10,
        JOB_STATUS_STEP1_RUNNING: 30,
        JOB_STATUS_STEP1_READY: 35,
        JOB_STATUS_STEP1_CONFIRMED: 45,
        JOB_STATUS_STEP2_RUNNING: 60,
        JOB_STATUS_STEP2_READY: 75,
        JOB_STATUS_STEP2_CONFIRMED: 80,
        JOB_STATUS_SUCCEEDED: 100,
        JOB_STATUS_FAILED: 0,
    }
    return int(mapping.get(status, 0))


def _normalize_meta_status(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    allowed = {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_STEP1_RUNNING,
        JOB_STATUS_STEP1_READY,
        JOB_STATUS_STEP1_CONFIRMED,
        JOB_STATUS_STEP2_RUNNING,
        JOB_STATUS_STEP2_READY,
        JOB_STATUS_STEP2_CONFIRMED,
        JOB_STATUS_SUCCEEDED,
        JOB_STATUS_FAILED,
    }
    return raw if raw in allowed else None


def _effective_status(meta_status: str | None, inferred_status: str) -> str:
    if meta_status == JOB_STATUS_STEP1_RUNNING and inferred_status in {JOB_STATUS_CREATED, JOB_STATUS_UPLOAD_READY}:
        return JOB_STATUS_STEP1_RUNNING
    if meta_status == JOB_STATUS_STEP2_RUNNING and inferred_status in {JOB_STATUS_STEP1_CONFIRMED}:
        return JOB_STATUS_STEP2_RUNNING
    if meta_status == JOB_STATUS_FAILED and inferred_status in {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_STEP1_RUNNING,
        JOB_STATUS_STEP2_RUNNING,
    }:
        return JOB_STATUS_FAILED
    return inferred_status


def create_job(job_id: str, status: str, owner_user_id: str) -> dict[str, Any]:
    normalized_status = _normalize_meta_status(status) or JOB_STATUS_CREATED
    now = now_iso()
    ensure_job_dirs(job_id)
    _write_json(
        _meta_path(job_id),
        {
            "job_id": job_id,
            "owner_user_id": owner_user_id,
            "status": normalized_status,
            "progress": _progress_for_status(normalized_status),
            "created_at": now,
            "updated_at": now,
        },
    )
    _write_files_manifest(job_id, {})
    _error_path(job_id).unlink(missing_ok=True)
    _step1_confirmed_path(job_id).unlink(missing_ok=True)
    _step2_confirmed_path(job_id).unlink(missing_ok=True)
    return get_job(job_id, owner_user_id=owner_user_id) or {
        "job_id": job_id,
        "status": JOB_STATUS_CREATED,
        "progress": 0,
        "error": None,
    }


def get_job(job_id: str, *, owner_user_id: str | None = None) -> dict[str, Any] | None:
    meta = _read_meta(job_id)
    if not meta:
        return None
    if owner_user_id and str(meta.get("owner_user_id") or "") != owner_user_id:
        return None

    inferred_status = _infer_job_status(job_id)
    meta_status = _normalize_meta_status(meta.get("status"))
    status = _effective_status(meta_status, inferred_status)
    meta_progress = meta.get("progress")
    try:
        progress_from_meta = int(meta_progress) if meta_progress is not None else None
    except Exception:
        progress_from_meta = None
    progress = _progress_for_status(status)
    if meta_status == status and progress_from_meta is not None:
        progress = max(0, min(100, progress_from_meta))
    error_payload = _read_json(_error_path(job_id))
    error: dict[str, str] | None = None
    if isinstance(error_payload, dict):
        code = str(error_payload.get("code") or "").strip()
        message = str(error_payload.get("message") or "").strip()
        if code:
            error = {"code": code, "message": message}

    return {
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "error": error,
    }


def get_job_owner_user_id(job_id: str) -> str | None:
    meta = _read_meta(job_id)
    if not isinstance(meta, dict):
        return None
    owner_user_id = str(meta.get("owner_user_id") or "").strip()
    return owner_user_id or None


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    meta = _read_meta(job_id)
    if not meta:
        return

    normalized_status = _normalize_meta_status(status)
    if normalized_status:
        meta["status"] = normalized_status
    if progress is not None:
        try:
            meta["progress"] = max(0, min(100, int(progress)))
        except Exception:
            pass
    meta["updated_at"] = now_iso()
    _write_json(_meta_path(job_id), meta)

    if normalized_status == JOB_STATUS_STEP1_CONFIRMED:
        _step1_confirmed_path(job_id).parent.mkdir(parents=True, exist_ok=True)
        _step1_confirmed_path(job_id).touch()
    elif normalized_status == JOB_STATUS_STEP2_CONFIRMED:
        _step2_confirmed_path(job_id).parent.mkdir(parents=True, exist_ok=True)
        _step2_confirmed_path(job_id).touch()
    elif normalized_status == JOB_STATUS_FAILED and error_code:
        _write_json(
            _error_path(job_id),
            {
                "code": str(error_code),
                "message": str(error_message or ""),
            },
        )
    elif normalized_status in {
        JOB_STATUS_CREATED,
        JOB_STATUS_UPLOAD_READY,
        JOB_STATUS_STEP1_RUNNING,
        JOB_STATUS_STEP1_READY,
        JOB_STATUS_STEP1_CONFIRMED,
        JOB_STATUS_STEP2_RUNNING,
        JOB_STATUS_STEP2_READY,
        JOB_STATUS_STEP2_CONFIRMED,
        JOB_STATUS_SUCCEEDED,
    }:
        _error_path(job_id).unlink(missing_ok=True)


def touch_job(job_id: str) -> None:
    meta = _read_meta(job_id)
    if not meta:
        return
    meta["updated_at"] = now_iso()
    _write_json(_meta_path(job_id), meta)


def get_job_files(job_id: str) -> dict[str, Any] | None:
    if not _meta_path(job_id).exists():
        return None
    return _normalize_files(job_id, _read_files_manifest(job_id))


def upsert_job_files(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    if not _meta_path(job_id).exists():
        return
    payload = _read_files_manifest(job_id)
    for field in JOB_FILE_FIELDS:
        if field in kwargs:
            value = kwargs[field]
            payload[field] = str(value) if isinstance(value, Path) else value
    _write_files_manifest(job_id, payload)
    touch_job(job_id)


def clear_step_data(job_id: str) -> None:
    _step1_lines_path(job_id).unlink(missing_ok=True)
    _step2_topics_path(job_id).unlink(missing_ok=True)


def _has_artifacts(files: dict[str, Any]) -> bool:
    for field in JOB_FILE_FIELDS:
        value = files.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _is_cleanup_candidate_status(status: str | None) -> bool:
    return status in {JOB_STATUS_SUCCEEDED, JOB_STATUS_STEP2_CONFIRMED}


def list_expired_succeeded_jobs(cutoff_updated_at: str, *, limit: int) -> list[str]:
    settings = get_settings()
    jobs_root = settings.work_dir / "jobs"
    if not jobs_root.exists():
        return []

    cutoff = _parse_iso(cutoff_updated_at)
    pairs: list[tuple[datetime, str]] = []
    for item in jobs_root.iterdir():
        if not item.is_dir():
            continue
        job_id = item.name
        meta = _read_meta(job_id)
        if not meta:
            continue
        status = _normalize_meta_status(meta.get("status"))
        if not _is_cleanup_candidate_status(status):
            continue
        files = get_job_files(job_id) or {}
        if not _has_artifacts(files):
            continue
        updated_at = _parse_iso(str(meta.get("updated_at") or meta.get("created_at") or ""))
        if updated_at <= cutoff:
            pairs.append((updated_at, job_id))

    pairs.sort(key=lambda pair: pair[0])
    return [job_id for _, job_id in pairs[: int(max(1, limit))]]


def list_succeeded_jobs_with_artifacts(*, limit: int) -> list[str]:
    settings = get_settings()
    jobs_root = settings.work_dir / "jobs"
    if not jobs_root.exists():
        return []

    pairs: list[tuple[datetime, str]] = []
    for item in jobs_root.iterdir():
        if not item.is_dir():
            continue
        job_id = item.name
        meta = _read_meta(job_id)
        if not meta:
            continue
        status = _normalize_meta_status(meta.get("status"))
        if not _is_cleanup_candidate_status(status):
            continue
        files = get_job_files(job_id) or {}
        if not _has_artifacts(files):
            continue
        updated_at = _parse_iso(str(meta.get("updated_at") or meta.get("created_at") or ""))
        pairs.append((updated_at, job_id))

    pairs.sort(key=lambda pair: pair[0])
    return [job_id for _, job_id in pairs[: int(max(1, limit))]]


def replace_step1_lines(job_id: str, lines: list[dict[str, Any]]) -> None:
    _write_json(_step1_lines_path(job_id), {"lines": lines})


def list_step1_lines(job_id: str) -> list[dict[str, Any]]:
    payload = _read_json(_step1_lines_path(job_id))
    if isinstance(payload, dict) and isinstance(payload.get("lines"), list):
        lines = payload["lines"]
    elif isinstance(payload, list):
        lines = payload
    else:
        lines = []

    normalized: list[dict[str, Any]] = []
    for row in lines:
        if not isinstance(row, dict):
            continue
        try:
            normalized.append(
                {
                    "line_id": int(row["line_id"]),
                    "start": float(row["start"]),
                    "end": float(row["end"]),
                    "original_text": str(row.get("original_text") or ""),
                    "optimized_text": str(row.get("optimized_text") or ""),
                    "ai_suggest_remove": bool(row.get("ai_suggest_remove", False)),
                    "user_final_remove": bool(row.get("user_final_remove", False)),
                }
            )
        except Exception:
            continue
    normalized.sort(key=lambda item: int(item["line_id"]))
    return normalized


def replace_step2_chapters(job_id: str, chapters: list[dict[str, Any]]) -> None:
    _write_json(_step2_topics_path(job_id), {"topics": chapters})


def list_step2_chapters(job_id: str) -> list[dict[str, Any]]:
    payload = _read_json(_step2_topics_path(job_id))
    if isinstance(payload, dict) and isinstance(payload.get("topics"), list):
        topics = payload["topics"]
    elif isinstance(payload, list):
        topics = payload
    else:
        topics = []

    result: list[dict[str, Any]] = []
    for row in topics:
        if not isinstance(row, dict):
            continue
        try:
            chapter_id = int(row.get("chapter_id", len(result) + 1))
            start = float(row.get("start", 0.0))
            end = float(row.get("end", 0.0))
            if end <= start:
                continue
        except Exception:
            continue

        line_ids_raw = row.get("line_ids")
        line_ids = [int(item) for item in line_ids_raw if isinstance(item, (int, float))] if isinstance(line_ids_raw, list) else []
        result.append(
            {
                "chapter_id": chapter_id,
                "title": str(row.get("title") or f"章节{chapter_id}"),
                "summary": str(row.get("summary") or ""),
                "start": start,
                "end": end,
                "line_ids": line_ids,
            }
        )
    result.sort(key=lambda item: int(item["chapter_id"]))
    return result
