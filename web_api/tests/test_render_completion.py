from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.constants import JOB_STATUS_STEP2_CONFIRMED, JOB_STATUS_SUCCEEDED
from web_api.db import get_conn, init_db
from web_api.repository import create_job, get_job, now_iso, update_job
from web_api.services.render_completion import mark_render_success


class RenderCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
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

    def test_mark_render_success_deducts_once_and_persists_succeeded_status(self) -> None:
        job_id = "job_render_done"
        user_id = "user_render_done"
        create_job(job_id, "CREATED", user_id)
        update_job(job_id, status=JOB_STATUS_STEP2_CONFIRMED)

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                VALUES(?, 2, 'TEST_CREDIT', NULL, ?, ?)
                """,
                (user_id, f"test-credit:{user_id}", now_iso()),
            )
            conn.commit()

        first = mark_render_success(job_id)
        second = mark_render_success(job_id)

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

    def test_mark_render_success_raises_when_credit_is_insufficient(self) -> None:
        job_id = "job_render_no_credit"
        user_id = "user_render_no_credit"
        create_job(job_id, "CREATED", user_id)
        update_job(job_id, status=JOB_STATUS_STEP2_CONFIRMED)

        with self.assertRaises(RuntimeError) as ctx:
            mark_render_success(job_id)

        self.assertEqual(str(ctx.exception), "额度不足，请先兑换邀请码后重试")
        job = get_job(job_id, owner_user_id=user_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_STEP2_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
