from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Any

from .constants import (
    JOB_STATUS_CREATED,
    JOB_STATUS_FAILED,
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_UPLOAD_READY,
)
from .db import get_conn, retry_turso_operation
from .user_identity import ensure_business_user
from .utils.persistence_helpers import now_iso, parse_iso_datetime_or_epoch

USER_STATUS_PENDING_COUPON = "PENDING_COUPON"
USER_STATUS_ACTIVE = "ACTIVE"
_STAGE_UNSET = object()

JOB_FILE_FIELDS = (
    "video_path",
    "audio_path",
    "asr_oss_key",
    "pending_asr_oss_key",
    "optimized_srt_oss_key",
    "optimized_srt_oss_signed_url",
    "srt_path",
    "asr_words_sidecar_path",
    "optimized_srt_path",
    "chapters_draft_path",
    "final_test_text_path",
    "final_test_srt_path",
    "final_chapters_path",
    "subtitle_render_v1_path",
    "final_video_path",
)

_STATUS_RANK = {
    JOB_STATUS_CREATED: 0,
    JOB_STATUS_UPLOAD_READY: 1,
    JOB_STATUS_TEST_RUNNING: 2,
    JOB_STATUS_TEST_READY: 3,
    JOB_STATUS_TEST_CONFIRMED: 4,
    JOB_STATUS_SUCCEEDED: 5,
    JOB_STATUS_FAILED: 6,
}


def _parse_iso(value: str | None) -> datetime:
    return parse_iso_datetime_or_epoch(value)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        pass
    try:
        return row[index]
    except Exception:
        return None


@retry_turso_operation("ensure user")
def ensure_user(user_id: str, email: str | None) -> None:
    with get_conn() as conn:
        result = ensure_business_user(conn, user_id=user_id, email=email)
        welcome_granted = _ensure_welcome_credit_in_tx(conn, result.target_user_id)
        if result.changed or welcome_granted:
            conn.commit()


def _ensure_welcome_credit_in_tx(conn: Any, user_id: str) -> bool:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id cannot be empty")

    existing = conn.execute(
        """
        SELECT entry_id
        FROM credit_ledger
        WHERE user_id = ? AND reason = 'WELCOME_CREDIT'
        LIMIT 1
        """,
        (normalized_user_id,),
    ).fetchone()
    if existing:
        return False

    now = now_iso()
    inserted = conn.execute(
        """
        INSERT OR IGNORE INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
        VALUES(?, 1, 'WELCOME_CREDIT', NULL, ?, ?)
        """,
        (normalized_user_id, f"welcome:{normalized_user_id}", now),
    )
    if int(getattr(inserted, "rowcount", 0) or 0) <= 0:
        return False

    conn.execute(
        """
        UPDATE users
        SET status = ?, activated_at = COALESCE(activated_at, ?), updated_at = ?
        WHERE user_id = ?
        """,
        (USER_STATUS_ACTIVE, now, now, normalized_user_id),
    )
    return True


@retry_turso_operation("get user")
def get_user(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, email, status, activated_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "user_id": str(_row_value(row, "user_id", 0)),
        "email": _row_value(row, "email", 1),
        "status": _row_value(row, "status", 2) or USER_STATUS_PENDING_COUPON,
        "activated_at": _row_value(row, "activated_at", 3),
    }


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def _generate_coupon_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(max(4, int(length))))
    return f"CPN-{token}"


def _generate_guest_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_tracking_value(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _create_coupon_in_tx(
    conn: Any,
    *,
    code: str,
    credits: int,
    expires_at: str | None,
    status: str,
    source: str | None,
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO coupon_codes(
            code,
            credits,
            used_count,
            expires_at,
            status,
            source,
            created_at,
            updated_at
        )
        VALUES(?, ?, 0, ?, ?, ?, ?, ?)
        """,
        (
            code,
            int(credits),
            expires_at,
            status,
            source,
            now,
            now,
        ),
    )


@retry_turso_operation("claim public coupon code")
def claim_public_coupon_code(
    ip_address: str,
    *,
    credits: int,
    source: str | None = "PUBLIC_WEB_INVITE",
) -> dict[str, Any]:
    normalized_ip = str(ip_address or "").strip()
    if not normalized_ip:
        raise ValueError("client ip cannot be empty")

    normalized_credits = int(credits)
    if normalized_credits <= 0:
        raise ValueError("credits must be positive")

    ip_hash = hashlib.sha256(normalized_ip.encode("utf-8")).hexdigest()
    normalized_source = (source or "").strip() or None

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        now = now_iso()

        claim = conn.execute(
            """
            SELECT code
            FROM public_invite_claims
            WHERE ip_hash = ?
            LIMIT 1
            """,
            (ip_hash,),
        ).fetchone()
        existing_code = str(_row_value(claim, "code", 0) or "").strip() if claim else ""
        has_existing_claim = bool(existing_code)
        if existing_code:
            coupon = conn.execute(
                """
                SELECT code, credits, used_count, expires_at, status
                FROM coupon_codes
                WHERE code = ?
                LIMIT 1
                """,
                (existing_code,),
            ).fetchone()
            if coupon:
                try:
                    _assert_coupon_usable_in_tx(coupon)
                except LookupError:
                    coupon = None
                else:
                    conn.execute(
                        "UPDATE public_invite_claims SET updated_at = ? WHERE ip_hash = ?",
                        (now, ip_hash),
                    )
                    conn.commit()
                    return {
                        "code": str(_row_value(coupon, "code", 0)),
                        "credits": int(_row_value(coupon, "credits", 1) or normalized_credits),
                        "already_claimed": True,
                    }

        if not has_existing_claim:
            settings_row = conn.execute(
                """
                SELECT max_claims
                FROM public_invite_settings
                WHERE settings_id = 1
                LIMIT 1
                """
            ).fetchone()
            max_claims = int(_row_value(settings_row, "max_claims", 0) or 0) if settings_row else 0
            claim_count_row = conn.execute(
                "SELECT COUNT(*) AS total FROM public_invite_claims"
            ).fetchone()
            claim_count = int(_row_value(claim_count_row, "total", 0) or 0) if claim_count_row else 0
            if max_claims > 0 and claim_count >= max_claims:
                conn.rollback()
                raise LookupError("PUBLIC_INVITE_EXHAUSTED")

        generated_code = ""
        last_error: Exception | None = None
        for _attempt in range(20):
            try:
                generated_code = _generate_coupon_code()
                _create_coupon_in_tx(
                    conn,
                    code=generated_code,
                    credits=normalized_credits,
                    expires_at=None,
                    status="ACTIVE",
                    source=normalized_source,
                    now=now,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                generated_code = ""
        if not generated_code:
            conn.rollback()
            if last_error is not None:
                raise RuntimeError("failed to generate coupon") from last_error
            raise RuntimeError("failed to generate coupon")

        if has_existing_claim:
            conn.execute(
                """
                UPDATE public_invite_claims
                SET code = ?, updated_at = ?
                WHERE ip_hash = ?
                """,
                (generated_code, now, ip_hash),
            )
            already_claimed = True
        else:
            conn.execute(
                """
                INSERT INTO public_invite_claims(ip_hash, code, created_at, updated_at)
                VALUES(?, ?, ?, ?)
                """,
                (ip_hash, generated_code, now, now),
            )
            already_claimed = False

        conn.commit()
        return {
            "code": generated_code,
            "credits": normalized_credits,
            "already_claimed": already_claimed,
        }


def _row_to_guest_session(row: Any) -> dict[str, Any]:
    return {
        "guest_id": str(_row_value(row, "guest_id", 0) or "").strip(),
        "token_hash": str(_row_value(row, "token_hash", 1) or "").strip(),
        "device_fingerprint_hash": _row_value(row, "device_fingerprint_hash", 2),
        "ip_hash": str(_row_value(row, "ip_hash", 3) or "").strip(),
        "user_agent_hash": _row_value(row, "user_agent_hash", 4),
        "free_uses_remaining": int(_row_value(row, "free_uses_remaining", 5) or 0),
        "status": str(_row_value(row, "status", 6) or "ACTIVE").upper(),
        "job_id": _row_value(row, "job_id", 7),
        "consumed_at": _row_value(row, "consumed_at", 8),
        "created_at": _row_value(row, "created_at", 9),
        "updated_at": _row_value(row, "updated_at", 10),
    }


def _load_guest_session_in_tx(
    conn: Any,
    *,
    guest_id: str | None = None,
    token_hash: str | None = None,
    device_fingerprint_hash: str | None = None,
    ip_hash: str | None = None,
    user_agent_hash: str | None = None,
) -> dict[str, Any] | None:
    row = None
    if guest_id:
        row = conn.execute(
            """
            SELECT guest_id, token_hash, device_fingerprint_hash, ip_hash, user_agent_hash,
                   free_uses_remaining, status, job_id, consumed_at, created_at, updated_at
            FROM guest_sessions
            WHERE guest_id = ?
            LIMIT 1
            """,
            (guest_id,),
        ).fetchone()
    elif token_hash:
        row = conn.execute(
            """
            SELECT guest_id, token_hash, device_fingerprint_hash, ip_hash, user_agent_hash,
                   free_uses_remaining, status, job_id, consumed_at, created_at, updated_at
            FROM guest_sessions
            WHERE token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
    elif device_fingerprint_hash:
        row = conn.execute(
            """
            SELECT guest_id, token_hash, device_fingerprint_hash, ip_hash, user_agent_hash,
                   free_uses_remaining, status, job_id, consumed_at, created_at, updated_at
            FROM guest_sessions
            WHERE device_fingerprint_hash = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (device_fingerprint_hash,),
        ).fetchone()
    elif ip_hash:
        if user_agent_hash:
            row = conn.execute(
                """
                SELECT guest_id, token_hash, device_fingerprint_hash, ip_hash, user_agent_hash,
                       free_uses_remaining, status, job_id, consumed_at, created_at, updated_at
                FROM guest_sessions
                WHERE ip_hash = ? AND user_agent_hash = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (ip_hash, user_agent_hash),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT guest_id, token_hash, device_fingerprint_hash, ip_hash, user_agent_hash,
                       free_uses_remaining, status, job_id, consumed_at, created_at, updated_at
                FROM guest_sessions
                WHERE ip_hash = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (ip_hash,),
            ).fetchone()
    if not row:
        return None
    return _row_to_guest_session(row)


@retry_turso_operation("claim guest session")
def claim_guest_session(
    *,
    ip_address: str,
    user_agent: str | None,
    device_fingerprint: str | None,
) -> dict[str, Any]:
    normalized_ip = str(ip_address or "").strip()
    if not normalized_ip:
        raise ValueError("client ip cannot be empty")

    ip_hash = _hash_tracking_value(normalized_ip)
    user_agent_hash = _hash_tracking_value(user_agent)
    fingerprint_hash = _hash_tracking_value(device_fingerprint)
    now = now_iso()

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")

        existing = None
        if fingerprint_hash:
            existing = _load_guest_session_in_tx(
                conn,
                device_fingerprint_hash=fingerprint_hash,
            )
        if existing is None and ip_hash:
            existing = _load_guest_session_in_tx(
                conn,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
            )

        guest_token = _generate_guest_token()
        token_hash = _hash_tracking_value(guest_token)
        if not token_hash:
            conn.rollback()
            raise RuntimeError("failed to create guest token")

        if existing is not None:
            status = str(existing.get("status") or "ACTIVE").upper()
            remaining = int(existing.get("free_uses_remaining") or 0)
            if remaining < 1 or status != "ACTIVE":
                conn.rollback()
                raise LookupError("GUEST_SESSION_INELIGIBLE")

            conn.execute(
                """
                UPDATE guest_sessions
                SET token_hash = ?,
                    device_fingerprint_hash = COALESCE(device_fingerprint_hash, ?),
                    ip_hash = ?,
                    user_agent_hash = COALESCE(?, user_agent_hash),
                    updated_at = ?
                WHERE guest_id = ?
                """,
                (
                    token_hash,
                    fingerprint_hash,
                    ip_hash,
                    user_agent_hash,
                    now,
                    existing["guest_id"],
                ),
            )
            conn.commit()
            refreshed = _load_guest_session_in_tx(conn, guest_id=existing["guest_id"]) or existing
            return {
                "guest_id": str(refreshed["guest_id"]),
                "token": guest_token,
                "free_uses_remaining": int(refreshed["free_uses_remaining"]),
                "job_id": refreshed.get("job_id"),
                "reused_existing": True,
            }

        guest_id = f"gst_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT INTO guest_sessions(
                guest_id,
                token_hash,
                device_fingerprint_hash,
                ip_hash,
                user_agent_hash,
                free_uses_remaining,
                status,
                job_id,
                consumed_at,
                created_at,
                updated_at
            )
            VALUES(?, ?, ?, ?, ?, 1, 'ACTIVE', NULL, NULL, ?, ?)
            """,
            (
                guest_id,
                token_hash,
                fingerprint_hash,
                ip_hash,
                user_agent_hash,
                now,
                now,
            ),
        )
        conn.commit()
        return {
            "guest_id": guest_id,
            "token": guest_token,
            "free_uses_remaining": 1,
            "job_id": None,
            "reused_existing": False,
        }


@retry_turso_operation("get guest session by token")
def get_guest_session_by_token(token: str) -> dict[str, Any] | None:
    token_hash = _hash_tracking_value(token)
    if not token_hash:
        return None
    with get_conn() as conn:
        return _load_guest_session_in_tx(conn, token_hash=token_hash)


@retry_turso_operation("get guest session")
def get_guest_session(guest_id: str) -> dict[str, Any] | None:
    normalized_guest_id = str(guest_id or "").strip()
    if not normalized_guest_id:
        return None
    with get_conn() as conn:
        return _load_guest_session_in_tx(conn, guest_id=normalized_guest_id)


@retry_turso_operation("set guest session job")
def set_guest_session_job(guest_id: str, job_id: str | None) -> dict[str, Any]:
    normalized_guest_id = str(guest_id or "").strip()
    if not normalized_guest_id:
        raise ValueError("guest_id cannot be empty")
    normalized_job_id = str(job_id or "").strip() or None
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE guest_sessions
            SET job_id = ?, updated_at = ?
            WHERE guest_id = ?
            """,
            (normalized_job_id, now_iso(), normalized_guest_id),
        )
        conn.commit()
        session = _load_guest_session_in_tx(conn, guest_id=normalized_guest_id)
    if not session:
        raise LookupError("GUEST_SESSION_NOT_FOUND")
    return session


@retry_turso_operation("consume guest session free use")
def consume_guest_session_free_use(guest_id: str, job_id: str) -> dict[str, Any]:
    normalized_guest_id = str(guest_id or "").strip()
    normalized_job_id = str(job_id or "").strip()
    if not normalized_guest_id:
        raise ValueError("guest_id cannot be empty")
    if not normalized_job_id:
        raise ValueError("job_id cannot be empty")

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _load_guest_session_in_tx(conn, guest_id=normalized_guest_id)
        if not session:
            conn.rollback()
            raise LookupError("GUEST_SESSION_NOT_FOUND")

        remaining = int(session.get("free_uses_remaining") or 0)
        status = str(session.get("status") or "ACTIVE").upper()
        previous_job_id = str(session.get("job_id") or "").strip()
        if remaining < 1 or status != "ACTIVE":
            if previous_job_id == normalized_job_id:
                conn.commit()
                return {"consumed": False, "balance": 0}
            conn.rollback()
            raise LookupError("INSUFFICIENT_CREDITS")

        now = now_iso()
        conn.execute(
            """
            UPDATE guest_sessions
            SET free_uses_remaining = 0,
                status = 'CONSUMED',
                job_id = ?,
                consumed_at = ?,
                updated_at = ?
            WHERE guest_id = ?
            """,
            (normalized_job_id, now, now, normalized_guest_id),
        )
        conn.commit()
        return {"consumed": True, "balance": 0}


@retry_turso_operation("get credit balance")
def get_credit_balance(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    return int(_row_value(row, "balance", 0) or 0)


@retry_turso_operation("get recent credit ledger")
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
            "entry_id": int(_row_value(row, "entry_id", 0)),
            "delta": int(_row_value(row, "delta", 1)),
            "reason": str(_row_value(row, "reason", 2)),
            "job_id": _row_value(row, "job_id", 3),
            "idempotency_key": str(_row_value(row, "idempotency_key", 4)),
            "created_at": str(_row_value(row, "created_at", 5)),
        }
        for row in rows
    ]


@retry_turso_operation("consume test credit")
def consume_job_test_credit(user_id: str, job_id: str) -> dict[str, Any]:
    idempotency_key = f"job:{job_id}:test_run"
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
            VALUES(?, -1, 'JOB_TEST_RUN', ?, ?, ?)
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


@retry_turso_operation("check job credit consumed")
def has_job_credit_consumed(job_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT entry_id
            FROM credit_ledger
            WHERE job_id = ? AND delta < 0 AND reason IN ('JOB_TEST_RUN', 'JOB_EXPORT_SUCCESS')
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
    return bool(row)


@retry_turso_operation("consume export credit")
def consume_job_export_credit(user_id: str, job_id: str) -> dict[str, Any]:
    idempotency_key = f"job:{job_id}:export_success"
    now = now_iso()

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")

        test_run = conn.execute(
            """
            SELECT entry_id
            FROM credit_ledger
            WHERE job_id = ? AND delta < 0 AND reason = 'JOB_TEST_RUN'
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if test_run:
            balance = _get_balance_in_tx(conn, user_id)
            conn.commit()
            return {"consumed": False, "balance": balance}

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
            VALUES(?, -1, 'JOB_EXPORT_SUCCESS', ?, ?, ?)
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
    used_count = int(_row_value(coupon, "used_count", 2) or 0)
    if used_count >= 1:
        raise LookupError("COUPON_CODE_EXHAUSTED")

    status = str(_row_value(coupon, "status", 4) or "").upper()
    if status != "ACTIVE":
        raise LookupError("COUPON_CODE_INVALID")

    _assert_not_expired_or_invalid(_row_value(coupon, "expires_at", 3))


@retry_turso_operation("preview coupon code")
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
    credits = int(_row_value(coupon, "credits", 1) or 0)
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
            user_status = str(_row_value(user, "status", 1) or "").upper()
            already_activated = user_status == USER_STATUS_ACTIVE or bool(_row_value(user, "activated_at", 2))

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

        credits = int(_row_value(coupon, "credits", 1) or 0)
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
    return int(_row_value(row, "balance", 0) or 0)
