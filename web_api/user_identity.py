from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .job_file_repository import reassign_job_owner_user_ids
from .utils.persistence_helpers import now_iso, parse_iso_datetime_or_epoch

USER_STATUS_PENDING_COUPON = "PENDING_COUPON"
USER_STATUS_ACTIVE = "ACTIVE"
_USERS_EMAIL_UNIQUE_INDEX = "idx_users_email_ci_unique"


@dataclass(frozen=True)
class UserIdentityReconcileResult:
    target_user_id: str
    normalized_email: str | None
    merged_user_ids: tuple[str, ...]
    ledger_rows_reassigned: int
    jobs_reassigned: int
    changed: bool


def normalize_email(raw: str | None) -> str | None:
    normalized = str(raw or "").strip().lower()
    return normalized or None


def ensure_user_identity_schema(conn: Any) -> int:
    _prefer_row_mapping(conn)
    reconciled = reconcile_user_identities(conn)
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_USERS_EMAIL_UNIQUE_INDEX}
        ON users(lower(email))
        WHERE email IS NOT NULL AND TRIM(email) <> ''
        """
    )
    return reconciled


def reconcile_user_identities(conn: Any) -> int:
    normalized_targets: dict[str, str | None] = {}

    for row in conn.execute(
        """
        SELECT lower(email) AS normalized_email
        FROM users
        WHERE email IS NOT NULL AND TRIM(email) <> ''
        GROUP BY lower(email)
        HAVING COUNT(*) > 1
        """
    ).fetchall():
        normalized_email = normalize_email(row["normalized_email"])
        if normalized_email:
            normalized_targets[normalized_email] = None

    if _table_exists(conn, "user"):
        for row in conn.execute(
            """
            SELECT id, lower(email) AS normalized_email
            FROM "user"
            WHERE email IS NOT NULL AND TRIM(email) <> ''
            """
        ).fetchall():
            normalized_email = normalize_email(row["normalized_email"])
            target_user_id = str(row["id"] or "").strip()
            if not normalized_email or not target_user_id:
                continue
            business_user_ids = {
                str(item["user_id"] or "").strip()
                for item in _load_business_rows_by_email(conn, normalized_email)
            }
            if not business_user_ids:
                continue
            if business_user_ids != {target_user_id}:
                normalized_targets[normalized_email] = target_user_id

    reconciled = 0
    for normalized_email, target_user_id in normalized_targets.items():
        result = consolidate_business_user_email(
            conn,
            normalized_email=normalized_email,
            preferred_user_id=target_user_id,
            create_missing=bool(target_user_id),
        )
        if result.changed:
            reconciled += 1
    return reconciled


def ensure_business_user(conn: Any, *, user_id: str, email: str | None) -> UserIdentityReconcileResult:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id cannot be empty")

    normalized_email = normalize_email(email)
    if normalized_email is None:
        row = _load_business_row(conn, normalized_user_id)
        if row is None:
            now = now_iso()
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
                VALUES(?, NULL, ?, NULL, ?, ?)
                """,
                (normalized_user_id, USER_STATUS_PENDING_COUPON, now, now),
            )
            return UserIdentityReconcileResult(
                target_user_id=normalized_user_id,
                normalized_email=None,
                merged_user_ids=(normalized_user_id,),
                ledger_rows_reassigned=0,
                jobs_reassigned=0,
                changed=True,
            )
        return UserIdentityReconcileResult(
            target_user_id=normalized_user_id,
            normalized_email=normalize_email(row["email"]),
            merged_user_ids=(normalized_user_id,),
            ledger_rows_reassigned=0,
            jobs_reassigned=0,
            changed=False,
        )

    return consolidate_business_user_email(
        conn,
        normalized_email=normalized_email,
        preferred_user_id=normalized_user_id,
        create_missing=True,
    )


def consolidate_business_user_email(
    conn: Any,
    *,
    normalized_email: str,
    preferred_user_id: str | None = None,
    create_missing: bool = False,
) -> UserIdentityReconcileResult:
    normalized_email = normalize_email(normalized_email)
    if normalized_email is None:
        raise ValueError("normalized_email cannot be empty")

    target_user_id = _select_target_user_id(
        conn,
        normalized_email=normalized_email,
        preferred_user_id=preferred_user_id,
    )
    if target_user_id is None:
        raise ValueError("target_user_id cannot be resolved")

    rows_by_user_id: dict[str, dict[str, Any]] = {}
    for row in _load_business_rows_by_email(conn, normalized_email):
        rows_by_user_id[str(row["user_id"])] = row
    target_row = _load_business_row(conn, target_user_id)
    if target_row is not None:
        rows_by_user_id[target_user_id] = target_row

    if not rows_by_user_id and not create_missing:
        return UserIdentityReconcileResult(
            target_user_id=target_user_id,
            normalized_email=normalized_email,
            merged_user_ids=(target_user_id,),
            ledger_rows_reassigned=0,
            jobs_reassigned=0,
            changed=False,
        )

    now = now_iso()
    existing_ids = set(rows_by_user_id.keys())
    merged_rows = list(rows_by_user_id.values())
    merged_user_ids = tuple(sorted(existing_ids | {target_user_id}))
    source_user_ids = tuple(sorted(user_id for user_id in existing_ids if user_id != target_user_id))

    merged_status = USER_STATUS_PENDING_COUPON
    if any(_is_active_business_row(row) for row in merged_rows):
        merged_status = USER_STATUS_ACTIVE

    activated_candidates = [str(row["activated_at"]) for row in merged_rows if row["activated_at"]]
    merged_activated_at = min(activated_candidates) if activated_candidates else None

    created_candidates = [str(row["created_at"]) for row in merged_rows if row["created_at"]]
    merged_created_at = _min_iso_or_now(created_candidates, now)

    updated_candidates = [str(row["updated_at"]) for row in merged_rows if row["updated_at"]]
    merged_updated_at = _max_iso_or_now(updated_candidates, now)

    target_exists = target_row is not None
    changed = False

    if source_user_ids:
        cursor = conn.execute(
            f"""
            UPDATE credit_ledger
            SET user_id = ?
            WHERE user_id IN ({",".join("?" for _ in source_user_ids)})
            """,
            (target_user_id, *source_user_ids),
        )
        ledger_rows_reassigned = int(getattr(cursor, "rowcount", 0) or 0)
        jobs_reassigned = reassign_job_owner_user_ids(source_user_ids, target_user_id)
        conn.execute(
            f"""
            DELETE FROM users
            WHERE user_id IN ({",".join("?" for _ in source_user_ids)})
            """,
            source_user_ids,
        )
        changed = True
    else:
        ledger_rows_reassigned = 0
        jobs_reassigned = 0

    if target_exists:
        row = target_row
        should_update_target = (
            normalize_email(row["email"]) != normalized_email
            or str(row["status"] or USER_STATUS_PENDING_COUPON).upper() != merged_status
            or str(row["activated_at"] or "") != str(merged_activated_at or "")
            or str(row["created_at"] or "") != merged_created_at
            or str(row["updated_at"] or "") != merged_updated_at
        )
        if should_update_target:
            conn.execute(
                """
                UPDATE users
                SET email = ?, status = ?, activated_at = ?, created_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    normalized_email,
                    merged_status,
                    merged_activated_at,
                    merged_created_at,
                    merged_updated_at,
                    target_user_id,
                ),
            )
            changed = True
    else:
        conn.execute(
            """
            INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                target_user_id,
                normalized_email,
                merged_status,
                merged_activated_at,
                merged_created_at,
                merged_updated_at,
            ),
        )
        changed = True

    return UserIdentityReconcileResult(
        target_user_id=target_user_id,
        normalized_email=normalized_email,
        merged_user_ids=merged_user_ids,
        ledger_rows_reassigned=ledger_rows_reassigned,
        jobs_reassigned=jobs_reassigned,
        changed=changed,
    )


def _select_target_user_id(
    conn: Any,
    *,
    normalized_email: str,
    preferred_user_id: str | None,
) -> str | None:
    normalized_preferred = str(preferred_user_id or "").strip() or None
    if normalized_preferred:
        return normalized_preferred

    auth_user_id = _load_auth_user_id(conn, normalized_email)
    if auth_user_id:
        return auth_user_id

    rows = _load_business_rows_by_email(conn, normalized_email)
    if not rows:
        return None

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, float, float, str]:
        activated = bool(row["activated_at"])
        active = str(row["status"] or "").upper() == USER_STATUS_ACTIVE
        return (
            0 if active else 1,
            0 if activated else 1,
            0 if normalize_email(row["email"]) == normalized_email else 1,
            -_parse_iso_timestamp(row["updated_at"]),
            _parse_iso_timestamp(row["created_at"]),
            str(row["user_id"]),
        )

    rows.sort(key=sort_key)
    return str(rows[0]["user_id"])


def _load_auth_user_id(conn: Any, normalized_email: str) -> str | None:
    if not _table_exists(conn, "user"):
        return None
    row = conn.execute(
        """
        SELECT id
        FROM "user"
        WHERE lower(email) = ?
        LIMIT 1
        """,
        (normalized_email,),
    ).fetchone()
    if not row:
        return None
    user_id = str(row["id"] or "").strip()
    return user_id or None


def _load_business_rows_by_email(conn: Any, normalized_email: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT user_id, email, status, activated_at, created_at, updated_at
        FROM users
        WHERE lower(email) = ?
        ORDER BY updated_at DESC, created_at DESC, user_id ASC
        """,
        (normalized_email,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_business_row(conn: Any, user_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT user_id, email, status, activated_at, created_at, updated_at
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def _is_active_business_row(row: dict[str, Any]) -> bool:
    if row.get("activated_at"):
        return True
    return str(row.get("status") or "").upper() == USER_STATUS_ACTIVE


def _min_iso_or_now(values: list[str], fallback: str) -> str:
    if not values:
        return fallback
    return min(values, key=_parse_iso_timestamp)


def _max_iso_or_now(values: list[str], fallback: str) -> str:
    if not values:
        return fallback
    return max(values, key=_parse_iso_timestamp)


def _parse_iso_timestamp(value: Any) -> float:
    try:
        return parse_iso_datetime_or_epoch(str(value or "")).timestamp()
    except Exception:
        return 0.0


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _prefer_row_mapping(conn: Any) -> None:
    try:
        if getattr(conn, "row_factory", None) is not sqlite3.Row:
            conn.row_factory = sqlite3.Row
    except Exception:
        return
