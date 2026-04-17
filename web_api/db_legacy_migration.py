from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .db import _extract_column_names, _table_exists, ensure_current_schema
from .user_identity import ensure_user_identity_schema


def migrate_legacy_schema_to_v2(conn: Any) -> None:
    ensure_current_schema(conn)

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
        WHERE status IS NULL
           OR TRIM(status) = ''
           OR status IN ('PENDING_INVITE', 'PENDING_ACTIVATION')
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
        legacy_coupon_columns = _extract_column_names(list(conn.execute("PRAGMA table_info(coupons)").fetchall()))
        if "code_plain" in legacy_coupon_columns:
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

    for table_name in (
        "job_tasks",
        "jobs",
        "job_files",
        "job_test_lines",
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

    ensure_user_identity_schema(conn)
    conn.commit()


def migrate_local_db_v1_to_v2(db_path: Path) -> None:
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        migrate_legacy_schema_to_v2(conn)
