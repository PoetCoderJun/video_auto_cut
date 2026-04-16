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
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["WORK_DIR"] = self.tmpdir.name
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

        self.assertTrue({"users", "coupon_codes", "credit_ledger", "public_invite_claims", "public_invite_settings"}.issubset(tables))
        self.assertEqual(settings_row, (1, 50))

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


class LegacyStep2JobMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["WORK_DIR"] = self.tmpdir.name
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
        (test_dir / "lines_draft.json").write_text(
            json.dumps(
                {
                    "lines": [
                        {
                            "line_id": 1,
                            "start": 0.0,
                            "end": 1.0,
                            "original_text": "第一句",
                            "optimized_text": "第一句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
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
        self.assertTrue((test_dir / "chapters_draft.json").exists())
        self.assertFalse((step2_dir / "topics.json").exists())

        files = json.loads(files_path.read_text(encoding="utf-8"))
        self.assertNotIn("topics_path", files)
        self.assertEqual(files["chapters_draft_path"], str((test_dir / "chapters_draft.json").resolve()))

        job = get_job(job_id, owner_user_id="user-1")
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_TEST_READY)
        self.assertIsNone(job["error"])


if __name__ == "__main__":
    unittest.main()
