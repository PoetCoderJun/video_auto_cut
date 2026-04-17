from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.constants import JOB_STATUS_TEST_READY
from web_api.db import init_db
from web_api.db_legacy_migration import migrate_local_db_v1_to_v2
from web_api.job_file_repository import create_job, get_job
from web_api.job_metadata_legacy_migration import migrate_legacy_step2_jobs


class LegacyDbMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ.pop("TURSO_LOCAL_REPLICA_PATH", None)
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_init_db_creates_current_schema_and_seed(self) -> None:
        init_db()

        db_path = get_settings().turso_local_replica_path
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            settings_row = conn.execute(
                "SELECT settings_id, max_claims FROM public_invite_settings"
            ).fetchone()
            email_indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(users)").fetchall()
            }

        self.assertTrue({"users", "coupon_codes", "credit_ledger", "public_invite_claims", "public_invite_settings"}.issubset(tables))
        self.assertEqual(settings_row, (1, 50))
        self.assertIn("idx_users_email_ci_unique", email_indexes)

    def test_migrate_local_db_v1_to_v2_repairs_legacy_schema(self) -> None:
        db_path = get_settings().turso_local_replica_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.unlink(missing_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT,
                    invite_activated_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                INSERT INTO users(user_id, email, invite_activated_at, created_at, updated_at)
                VALUES('user-1', 'user@example.com', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z');

                CREATE TABLE coupons (
                    coupon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_plain TEXT,
                    credits INTEGER NOT NULL,
                    redeemed_count INTEGER,
                    expires_at TEXT,
                    status TEXT,
                    source_user_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                INSERT INTO coupons(code_plain, credits, redeemed_count, expires_at, status, source_user_id, created_at, updated_at)
                VALUES('CPN-OLD', 5, 1, NULL, 'ACTIVE', 'legacy-source', '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z');

                CREATE TABLE coupon_redemptions (
                    redemption_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coupon_code TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    credits INTEGER NOT NULL,
                    redeemed_at TEXT NOT NULL
                );

                INSERT INTO coupon_redemptions(coupon_code, user_id, credits, redeemed_at)
                VALUES('CPN-OLD', 'user-1', 5, '2026-04-02T00:00:00Z');

                CREATE TABLE job_tasks (task_id INTEGER PRIMARY KEY);
                """
            )
            conn.commit()

        migrate_local_db_v1_to_v2(db_path)

        with sqlite3.connect(db_path) as conn:
            user_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            user_row = conn.execute(
                "SELECT status, activated_at FROM users WHERE user_id = 'user-1'"
            ).fetchone()
            coupon_row = conn.execute(
                "SELECT code, credits, used_count, status, source FROM coupon_codes WHERE code = 'CPN-OLD'"
            ).fetchone()
            ledger_row = conn.execute(
                "SELECT user_id, delta, reason, idempotency_key FROM credit_ledger WHERE user_id = 'user-1'"
            ).fetchone()
            legacy_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('job_tasks', 'coupons', 'coupon_redemptions')"
                ).fetchall()
            }

        self.assertIn("status", user_columns)
        self.assertIn("activated_at", user_columns)
        self.assertEqual(user_row, ("PENDING_COUPON", "2026-04-01T00:00:00Z"))
        self.assertEqual(coupon_row, ("CPN-OLD", 5, 1, "DISABLED", "legacy-source"))
        self.assertEqual(
            ledger_row,
            ("user-1", 5, "COUPON_REDEEM", "coupon:CPN-OLD:legacy:user-1"),
        )
        self.assertEqual(legacy_tables, set())

    def test_migrate_local_db_v1_to_v2_merges_duplicate_business_users_to_auth_user_id(self) -> None:
        db_path = get_settings().turso_local_replica_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.unlink(missing_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE "user" (
                    "id" text not null primary key,
                    "name" text not null,
                    "email" text not null unique,
                    "emailVerified" integer not null,
                    "image" text,
                    "createdAt" date not null,
                    "updatedAt" date not null
                );

                INSERT INTO "user"("id", "name", "email", "emailVerified", "createdAt", "updatedAt")
                VALUES('auth-user-1', 'User', 'user@example.com', 1, '2026-04-01T00:00:00Z', '2026-04-01T00:00:00Z');

                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING_INVITE',
                    invite_activated_at TEXT,
                    activated_at TEXT
                );

                INSERT INTO users(user_id, email, created_at, updated_at, status, activated_at)
                VALUES
                    ('legacy-user', 'user@example.com', '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z', 'ACTIVE', '2026-03-01T00:00:00Z'),
                    ('duplicate-user', 'USER@example.com', '2026-03-02T00:00:00Z', '2026-03-02T00:00:00Z', 'PENDING_INVITE', NULL);

                CREATE TABLE credit_ledger (
                    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    job_id TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                VALUES
                    ('legacy-user', 100, 'ADMIN_MANUAL_CREDIT', NULL, 'grant:legacy', '2026-03-03T00:00:00Z'),
                    ('duplicate-user', -1, 'JOB_STEP1_SUCCESS', 'job-1', 'job:1', '2026-03-04T00:00:00Z');
                """
            )
            conn.commit()

        migrate_local_db_v1_to_v2(db_path)

        with sqlite3.connect(db_path) as conn:
            users = conn.execute(
                "SELECT user_id, email, status, activated_at FROM users"
            ).fetchall()
            ledger_users = {
                row[0]
                for row in conn.execute("SELECT DISTINCT user_id FROM credit_ledger").fetchall()
            }

        self.assertEqual(users, [("auth-user-1", "user@example.com", "ACTIVE", "2026-03-01T00:00:00Z")])
        self.assertEqual(ledger_users, {"auth-user-1"})


class LegacyStep2JobMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ.pop("TURSO_LOCAL_REPLICA_PATH", None)
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_migrate_legacy_step2_jobs_moves_topics_into_test_workspace(self) -> None:
        job_id = "job_legacy_step2"
        create_job(job_id, "CREATED", "user-1")
        job_root = Path(self.tmpdir.name) / "jobs" / job_id
        test_dir = job_root / "test"
        step2_dir = job_root / "step2"
        test_dir.mkdir(parents=True, exist_ok=True)
        step2_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
        (step2_dir / "topics.json").write_text(
            json.dumps({"topics": [{"chapter_id": 1, "title": "开场", "block_range": "1"}]}, ensure_ascii=False),
            encoding="utf-8",
        )

        meta_path = job_root / "job.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "STEP2_READY"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        files_path = job_root / "job.files.json"
        files_path.write_text(
            json.dumps({"topics_path": str(step2_dir / "topics.json")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = migrate_legacy_step2_jobs(Path(self.tmpdir.name) / "jobs")

        self.assertEqual(result.jobs_migrated, 1)
        self.assertTrue((test_dir / "chapters_draft.txt").exists())
        self.assertFalse((step2_dir / "topics.json").exists())

        files = json.loads(files_path.read_text(encoding="utf-8"))
        self.assertNotIn("topics_path", files)
        self.assertEqual(files["chapters_draft_path"], str((test_dir / "chapters_draft.txt").resolve()))

        job = get_job(job_id, owner_user_id="user-1")
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_TEST_READY)
        self.assertIsNone(job["error"])


if __name__ == "__main__":
    unittest.main()
