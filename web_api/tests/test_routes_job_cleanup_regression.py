from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web_api.app import create_app
from web_api.config import get_settings
from web_api.db import get_conn, init_db
from web_api.job_file_repository import create_job, get_job, update_job, upsert_job_files
from web_api.utils.persistence_helpers import now_iso


class RoutesJobCleanupRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "WEB_AUTH_ENABLED": os.environ.get("WEB_AUTH_ENABLED"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ["WEB_AUTH_ENABLED"] = "0"
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_create_job_endpoint_returns_created_job_payload(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/jobs")

        self.assertEqual(response.status_code, 200)
        job = response.json()["data"]["job"]
        self.assertTrue(str(job["job_id"]).startswith("job_"))
        self.assertEqual(job["status"], "CREATED")
        self.assertEqual(job["progress"], 0)
        self.assertIsNone(job["stage"])
        self.assertIsNone(job["error"])

    def test_test_run_endpoint_accepts_and_marks_job_running(self) -> None:
        with (
            patch("web_api.api.routes.require_active_user", return_value=None),
            patch("web_api.api.routes.run_test_job_background", return_value=None) as mock_run_test_job_background,
            TestClient(create_app()) as client,
        ):
            create_response = client.post("/api/v1/jobs")
            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["data"]["job"]["job_id"]

            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
                    VALUES(?, 1, 'TEST_CREDIT', NULL, ?, ?)
                    """,
                    ("dev_local_user", "test-credit:dev_local_user", now_iso()),
                )
                conn.commit()

            upsert_job_files(job_id, asr_oss_key=f"video-auto-cut/asr/{job_id}/audio.wav")
            update_job(job_id, status="UPLOAD_READY", progress=20)

            response = client.post(f"/api/v1/jobs/{job_id}/test/run")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["job"]["job_id"], job_id)
        self.assertEqual(payload["job"]["status"], "TEST_RUNNING")
        self.assertEqual(payload["job"]["progress"], 30)
        self.assertEqual(payload["job"]["stage"]["code"], "TEST_QUEUED")
        mock_run_test_job_background.assert_called_once_with(job_id)

        job = get_job(job_id, owner_user_id="dev_local_user")
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "TEST_RUNNING")
        self.assertEqual(job["progress"], 30)

    def test_startup_recovers_interrupted_test_run_to_upload_ready(self) -> None:
        job_id = "job_interrupted_test"
        create_job(job_id, "CREATED", "dev_local_user")
        upsert_job_files(job_id, asr_oss_key=f"video-auto-cut/asr/{job_id}/audio.wav")
        update_job(
            job_id,
            status="TEST_RUNNING",
            progress=30,
            stage_code="TEST_QUEUED",
            stage_message="上传完成，正在启动字幕与章节生成...",
        )

        with TestClient(create_app()):
            pass

        job = get_job(job_id, owner_user_id="dev_local_user")
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "UPLOAD_READY")
        self.assertEqual(job["progress"], 10)
        self.assertEqual(job["stage"]["code"], "TEST_RETRY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
