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
    JOB_STATUS_STEP1_READY,
    TASK_TYPE_STEP1,
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
        (step1_dir / "final_chapters.json").write_text('{"topics":[]}', encoding="utf-8")
        (step1_dir / ".confirmed").touch()
        update_job(
            job_id,
            status=JOB_STATUS_STEP1_CONFIRMED,
            progress=45,
            stage_code="EXPORT_READY",
            stage_message="字幕和章节已确认，正在准备导出...",
        )

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["progress"], 45)
        self.assertEqual(job["error"]["code"], JOB_ERROR_CODE_FILES_MISSING)
        self.assertEqual(job["error"]["message"], JOB_ERROR_MESSAGE_FILES_MISSING)
        self.assertIsNone(job["stage"])

    def test_get_job_marks_step1_ready_without_chapters_draft_as_failed(self) -> None:
        job_id = "job_missing_step1_chapters_draft"
        create_job(job_id, "CREATED", "user-1")
        step1_dir = Path(self.tmpdir.name) / "jobs" / job_id / "step1"
        step1_dir.mkdir(parents=True, exist_ok=True)
        (step1_dir / "lines_draft.json").write_text("[]", encoding="utf-8")
        update_job(job_id, status=JOB_STATUS_STEP1_READY, progress=35)

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["progress"], 35)
        self.assertEqual(job["error"]["code"], JOB_ERROR_CODE_FILES_MISSING)
        self.assertEqual(job["error"]["message"], JOB_ERROR_MESSAGE_FILES_MISSING)

    def test_get_job_rejects_legacy_step2_artifacts_after_cutover(self) -> None:
        job_id = "job_legacy_step2"
        create_job(job_id, "CREATED", "user-1")
        step2_dir = Path(self.tmpdir.name) / "jobs" / job_id / "step2"
        step2_dir.mkdir(parents=True, exist_ok=True)
        (step2_dir / "final_topics.json").write_text('{"topics":[]}', encoding="utf-8")
        update_job(job_id, status="STEP2_READY", progress=75)

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["error"]["code"], "INVALID_STEP_STATE")
        self.assertEqual(job["error"]["message"], "任务流程已升级，请重新上传并重新生成字幕与章节。")


class TaskMissingFilesErrorTests(unittest.TestCase):
    @patch("web_api.services.tasks.set_task_failed")
    @patch("web_api.services.tasks.update_job")
    def test_execute_task_exposes_missing_files_as_public_job_error(
        self,
        mock_update_job,
        mock_set_task_failed,
    ) -> None:
        def fail_step1(_: str) -> None:
            raise RuntimeError("job files missing for step1")

        with patch.dict("web_api.services.tasks.TASK_DISPATCH", {TASK_TYPE_STEP1: fail_step1}, clear=False):
            execute_task({"task_id": 7, "job_id": "job-123", "task_type": TASK_TYPE_STEP1})

        mock_set_task_failed.assert_called_once_with(7, "job files missing for step1")
        mock_update_job.assert_called_once_with(
            "job-123",
            status=JOB_STATUS_FAILED,
            error_code=JOB_ERROR_CODE_FILES_MISSING,
            error_message=JOB_ERROR_MESSAGE_FILES_MISSING,
        )

    @patch("web_api.services.tasks.set_task_failed")
    @patch("web_api.services.tasks.update_job")
    def test_execute_task_rejects_legacy_step2_task_after_cutover(
        self,
        mock_update_job,
        mock_set_task_failed,
    ) -> None:
        execute_task({"task_id": 8, "job_id": "job-456", "task_type": "STEP2"})

        mock_set_task_failed.assert_called_once_with(8, "unsupported task type: STEP2")
        mock_update_job.assert_called_once_with(
            "job-456",
            status=JOB_STATUS_FAILED,
            error_code="INTERNAL_ERROR",
            error_message="unsupported task",
        )


if __name__ == "__main__":
    unittest.main()
