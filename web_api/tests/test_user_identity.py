from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from web_api.config import get_settings
from web_api.db import init_db
from web_api.db_repository import ensure_user, get_credit_balance
from web_api.job_file_repository import create_job, get_job_owner_user_id
from web_api.user_identity import _load_business_rows_by_email


class UserIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_ensure_user_merges_duplicate_email_rows_and_job_ownership(self) -> None:
        job_id = "job_duplicate_owner"
        create_job(job_id, "CREATED", "legacy-user")

        db_path = get_settings().turso_local_replica_path
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("DROP INDEX IF EXISTS idx_users_email_ci_unique")
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
                VALUES
                    ('legacy-user', 'same@example.com', 'ACTIVE', '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z'),
                    ('duplicate-user', 'same@example.com', 'PENDING_COUPON', NULL, '2026-03-02T00:00:00Z', '2026-03-02T00:00:00Z')
                """
            )
            conn.execute(
                """
                INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                VALUES
                    ('legacy-user', 20, 'ADMIN_MANUAL_CREDIT', NULL, 'grant:legacy', '2026-03-03T00:00:00Z'),
                    ('duplicate-user', 3, 'COUPON_REDEEM', NULL, 'coupon:dup', '2026-03-04T00:00:00Z')
                """
            )
            conn.commit()

        ensure_user("auth-user-1", "same@example.com")

        with sqlite3.connect(db_path) as conn:
            users = conn.execute(
                "SELECT user_id, email, status, activated_at FROM users ORDER BY user_id"
            ).fetchall()
            ledger_user_ids = {
                row[0]
                for row in conn.execute("SELECT DISTINCT user_id FROM credit_ledger").fetchall()
            }

        self.assertEqual(users, [("auth-user-1", "same@example.com", "ACTIVE", "2026-03-01T00:00:00Z")])
        self.assertEqual(ledger_user_ids, {"auth-user-1"})
        self.assertEqual(get_credit_balance("auth-user-1"), 23)
        self.assertEqual(get_job_owner_user_id(job_id), "auth-user-1")

    def test_init_db_reconciles_to_auth_user_id_before_unique_index_creation(self) -> None:
        db_path = get_settings().turso_local_replica_path
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS "user" (
                    "id" text not null primary key,
                    "name" text not null,
                    "email" text not null unique,
                    "emailVerified" integer not null,
                    "image" text,
                    "createdAt" date not null,
                    "updatedAt" date not null
                )
                """
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO "user"("id", "name", "email", "emailVerified", "createdAt", "updatedAt")
                VALUES('auth-user-2', 'User', 'owner@example.com', 1, '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z')
                """
            )
            conn.execute("DROP INDEX IF EXISTS idx_users_email_ci_unique")
            conn.execute("DELETE FROM users")
            conn.execute(
                """
                INSERT INTO users(user_id, email, status, activated_at, created_at, updated_at)
                VALUES
                    ('old-a', 'owner@example.com', 'ACTIVE', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z'),
                    ('old-b', 'OWNER@example.com', 'PENDING_COUPON', NULL, '2026-04-02T00:00:00Z', '2026-04-02T00:00:00Z')
                """
            )
            conn.commit()

        init_db()

        with sqlite3.connect(db_path) as conn:
            users = conn.execute(
                "SELECT user_id, email, status FROM users ORDER BY user_id"
            ).fetchall()
            indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(users)").fetchall()
            }

        self.assertEqual(users, [("auth-user-2", "owner@example.com", "ACTIVE")])
        self.assertIn("idx_users_email_ci_unique", indexes)

    def test_load_business_rows_by_email_accepts_tuple_rows(self) -> None:
        class _FakeCursor:
            def fetchall(self) -> list[tuple[str, str, str, str | None, str, str]]:
                return [
                    (
                        "tuple-user",
                        "tuple@example.com",
                        "ACTIVE",
                        "2026-04-01T00:00:00Z",
                        "2026-04-01T00:00:00Z",
                        "2026-04-01T00:00:00Z",
                    )
                ]

        class _FakeConn:
            def execute(self, _sql: str, _params: Any) -> _FakeCursor:
                return _FakeCursor()

        rows = _load_business_rows_by_email(_FakeConn(), "tuple@example.com")
        self.assertEqual(
            rows,
            [
                {
                    "user_id": "tuple-user",
                    "email": "tuple@example.com",
                    "status": "ACTIVE",
                    "activated_at": "2026-04-01T00:00:00Z",
                    "created_at": "2026-04-01T00:00:00Z",
                    "updated_at": "2026-04-01T00:00:00Z",
                }
            ],
        )
