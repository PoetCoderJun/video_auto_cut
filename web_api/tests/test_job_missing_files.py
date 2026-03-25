from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.config import get_settings
from web_api.constants import (
    JOB_ERROR_CODE_FILES_MISSING,
    JOB_ERROR_MESSAGE_FILES_MISSING,
    JOB_STATUS_FAILED,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP2_READY,
    TASK_TYPE_STEP2,
)
from web_api.repository import create_job, get_job, update_job
from web_api.services.tasks import execute_task


class JobMissingFilesTests(unittest.TestCase):
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

    def test_get_job_marks_step1_confirmed_without_final_srt_as_failed(self) -> None:
        job_id = "job_missing_step1_srt"
        create_job(job_id, "CREATED", "user-1")
        step1_dir = Path(self.tmpdir.name) / "jobs" / job_id / "step1"
        step1_dir.mkdir(parents=True, exist_ok=True)
        (step1_dir / "final_step1.json").write_text("[]", encoding="utf-8")
        update_job(
            job_id,
            status=JOB_STATUS_STEP1_CONFIRMED,
            progress=45,
            stage_code="GENERATING_CHAPTERS",
            stage_message="正在生成章节结构...",
        )

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["progress"], 45)
        self.assertEqual(job["error"]["code"], JOB_ERROR_CODE_FILES_MISSING)
        self.assertEqual(job["error"]["message"], JOB_ERROR_MESSAGE_FILES_MISSING)
        self.assertIsNone(job["stage"])

    def test_get_job_marks_step2_ready_without_step1_srt_as_failed(self) -> None:
        job_id = "job_missing_step2_input_srt"
        create_job(job_id, "CREATED", "user-1")
        step1_dir = Path(self.tmpdir.name) / "jobs" / job_id / "step1"
        step1_dir.mkdir(parents=True, exist_ok=True)
        (step1_dir / "final_step1.json").write_text("[]", encoding="utf-8")
        update_job(job_id, status=JOB_STATUS_STEP2_READY, progress=75)

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["progress"], 75)
        self.assertEqual(job["error"]["code"], JOB_ERROR_CODE_FILES_MISSING)
        self.assertEqual(job["error"]["message"], JOB_ERROR_MESSAGE_FILES_MISSING)


class TaskMissingFilesErrorTests(unittest.TestCase):
    @patch("web_api.services.tasks.set_task_failed")
    @patch("web_api.services.tasks.update_job")
    def test_execute_task_exposes_missing_files_as_public_job_error(
        self,
        mock_update_job,
        mock_set_task_failed,
    ) -> None:
        def fail_step2(_: str) -> None:
            raise RuntimeError("job files missing for step2")

        with patch.dict("web_api.services.tasks.TASK_DISPATCH", {TASK_TYPE_STEP2: fail_step2}, clear=False):
            execute_task({"task_id": 7, "job_id": "job-123", "task_type": TASK_TYPE_STEP2})

        mock_set_task_failed.assert_called_once_with(7, "job files missing for step2")
        mock_update_job.assert_called_once_with(
            "job-123",
            status=JOB_STATUS_FAILED,
            error_code=JOB_ERROR_CODE_FILES_MISSING,
            error_message=JOB_ERROR_MESSAGE_FILES_MISSING,
        )


if __name__ == "__main__":
    unittest.main()
