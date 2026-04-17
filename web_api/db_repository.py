from __future__ import annotations

import hashlib
import secrets
import string
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
    "optimized_srt_path",
    "chapters_draft_path",
    "final_test_text_path",
    "final_test_srt_path",
    "final_chapters_path",
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


@retry_turso_operation("ensure user")
def ensure_user(user_id: str, email: str | None) -> None:
    with get_conn() as conn:
        result = ensure_business_user(conn, user_id=user_id, email=email)
        if result.changed:
            conn.commit()


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
        "user_id": str(row["user_id"]),
        "email": row["email"],
        "status": row["status"] or USER_STATUS_PENDING_COUPON,
        "activated_at": row["activated_at"],
    }


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def _generate_coupon_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(max(4, int(length))))
    return f"CPN-{token}"


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
        existing_code = str(claim["code"] or "").strip() if claim else ""
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
                        "code": str(coupon["code"]),
                        "credits": int(coupon["credits"] or normalized_credits),
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
            max_claims = int(settings_row["max_claims"] or 0) if settings_row else 0
            claim_count_row = conn.execute(
                "SELECT COUNT(*) AS total FROM public_invite_claims"
            ).fetchone()
            claim_count = int(claim_count_row["total"] or 0) if claim_count_row else 0
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


@retry_turso_operation("get credit balance")
def get_credit_balance(user_id: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return 0
    return int(row["balance"] or 0)


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
            "entry_id": int(row["entry_id"]),
            "delta": int(row["delta"]),
            "reason": str(row["reason"]),
            "job_id": row["job_id"],
            "idempotency_key": str(row["idempotency_key"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


@retry_turso_operation("consume export credit")
def consume_job_export_credit(user_id: str, job_id: str) -> dict[str, Any]:
    idempotency_key = f"job:{job_id}:export_success"
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
    used_count = int(coupon["used_count"] or 0)
    if used_count >= 1:
        raise LookupError("COUPON_CODE_EXHAUSTED")

    status = str(coupon["status"] or "").upper()
    if status != "ACTIVE":
        raise LookupError("COUPON_CODE_INVALID")

    _assert_not_expired_or_invalid(coupon["expires_at"])


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
    credits = int(coupon["credits"] or 0)
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
            user_status = str(user["status"] or "").upper()
            already_activated = user_status == USER_STATUS_ACTIVE or bool(user["activated_at"])

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

        credits = int(coupon["credits"] or 0)
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
    return int(row["balance"] or 0)
