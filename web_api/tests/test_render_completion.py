from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.api.routes import render_complete
from web_api.config import get_settings
from web_api.constants import JOB_STATUS_TEST_CONFIRMED, JOB_STATUS_SUCCEEDED
from web_api.db import get_conn, init_db
from web_api.errors import ApiError
from web_api.job_file_repository import create_job, get_job, update_job
from web_api.services.auth import CurrentUser
from web_api.utils.persistence_helpers import now_iso


class RenderCompletionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        os.environ["WORK_DIR"] = self.tmpdir.name
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_render_complete_deducts_once_and_persists_succeeded_status(self) -> None:
        job_id = "job_render_done"
        user_id = "user_render_done"
        create_job(job_id, "CREATED", user_id)
        test_dir = Path(self.tmpdir.name) / "jobs" / job_id / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "final_test.txt").write_text("", encoding="utf-8")
        (test_dir / "final_test.srt").write_text("", encoding="utf-8")
        (test_dir / "final_chapters.txt").write_text("【1】开场\n", encoding="utf-8")
        (test_dir / ".confirmed").touch()
        update_job(job_id, status=JOB_STATUS_TEST_CONFIRMED)

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                VALUES(?, 2, 'TEST_CREDIT', NULL, ?, ?)
                """,
                (user_id, f"test-credit:{user_id}", now_iso()),
            )
            conn.commit()

        current_user = CurrentUser(user_id=user_id, email="user@example.com", account="user")
        with patch("web_api.api.routes.ensure_active_user", return_value=None):
            first = render_complete(job_id, current_user=current_user)["data"]["billing"]
            second = render_complete(job_id, current_user=current_user)["data"]["billing"]

        self.assertTrue(first["consumed"])
        self.assertEqual(first["balance"], 1)
        self.assertFalse(second["consumed"])
        self.assertEqual(second["balance"], 1)

        job = get_job(job_id, owner_user_id=user_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_SUCCEEDED)
        self.assertEqual(job["progress"], 100)
        self.assertEqual(job["stage"]["code"], "EXPORT_SUCCEEDED")

        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT delta, reason, idempotency_key
                FROM credit_ledger
                WHERE user_id = ? AND job_id = ?
                ORDER BY entry_id ASC
                """,
                (user_id, job_id),
            ).fetchall()

        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["delta"]), -1)
        self.assertEqual(str(rows[0]["reason"]), "JOB_EXPORT_SUCCESS")
        self.assertEqual(str(rows[0]["idempotency_key"]), f"job:{job_id}:export_success")

    def test_render_complete_raises_when_credit_is_insufficient(self) -> None:
        job_id = "job_render_no_credit"
        user_id = "user_render_no_credit"
        create_job(job_id, "CREATED", user_id)
        test_dir = Path(self.tmpdir.name) / "jobs" / job_id / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "final_test.txt").write_text("", encoding="utf-8")
        (test_dir / "final_test.srt").write_text("", encoding="utf-8")
        (test_dir / "final_chapters.txt").write_text("【1】开场\n", encoding="utf-8")
        (test_dir / ".confirmed").touch()
        update_job(job_id, status=JOB_STATUS_TEST_CONFIRMED)

        current_user = CurrentUser(user_id=user_id, email="user@example.com", account="user")
        with patch("web_api.api.routes.ensure_active_user", return_value=None):
            with self.assertRaises(ApiError) as ctx:
                render_complete(job_id, current_user=current_user)

        self.assertEqual(ctx.exception.code, "INVALID_STEP_STATE")
        self.assertEqual(ctx.exception.message, "额度不足，请先兑换邀请码后重试")
        job = get_job(job_id, owner_user_id=user_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_TEST_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
