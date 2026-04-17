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
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_READY,
    JOB_STATUS_UPLOAD_READY,
    PROGRESS_UPLOAD_READY,
)
from web_api.job_file_repository import create_job, get_job, update_job
from web_api.services.test_runner import recover_interrupted_test_runs, run_test_job_background


class _TempWorkDirTestCase(unittest.TestCase):
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


class JobMissingFilesTests(_TempWorkDirTestCase):

    def test_get_job_marks_test_confirmed_without_final_srt_as_failed(self) -> None:
        job_id = "job_missing_test_srt"
        create_job(job_id, "CREATED", "user-1")
        test_dir = Path(self.tmpdir.name) / "jobs" / job_id / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "final_test.txt").write_text("", encoding="utf-8")
        (test_dir / "final_chapters.txt").write_text("", encoding="utf-8")
        (test_dir / ".confirmed").touch()
        update_job(
            job_id,
            status=JOB_STATUS_TEST_CONFIRMED,
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

    def test_get_job_marks_test_ready_without_chapters_draft_as_failed(self) -> None:
        job_id = "job_missing_test_chapters_draft"
        create_job(job_id, "CREATED", "user-1")
        test_dir = Path(self.tmpdir.name) / "jobs" / job_id / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "lines_draft.txt").write_text("", encoding="utf-8")
        update_job(job_id, status=JOB_STATUS_TEST_READY, progress=35)

        job = get_job(job_id, owner_user_id="user-1")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], JOB_STATUS_FAILED)
        self.assertEqual(job["progress"], 35)
        self.assertEqual(job["error"]["code"], JOB_ERROR_CODE_FILES_MISSING)
        self.assertEqual(job["error"]["message"], JOB_ERROR_MESSAGE_FILES_MISSING)

class TestBackgroundRunnerTests(_TempWorkDirTestCase):
    @patch("web_api.services.test_runner.update_job")
    def test_run_test_job_background_exposes_missing_files_as_public_job_error(
        self,
        mock_update_job,
    ) -> None:
        def fail_test(_: str) -> None:
            raise RuntimeError("job files missing for test")

        with patch("web_api.services.test_runner.run_test", side_effect=fail_test):
            run_test_job_background("job-123")

        mock_update_job.assert_called_once_with(
            "job-123",
            status=JOB_STATUS_FAILED,
            error_code=JOB_ERROR_CODE_FILES_MISSING,
            error_message=JOB_ERROR_MESSAGE_FILES_MISSING,
        )

    @patch("web_api.services.test_runner.update_job")
    def test_run_test_job_background_resets_credit_failures_to_upload_ready(
        self,
        mock_update_job,
    ) -> None:
        with patch("web_api.services.test_runner.run_test", side_effect=RuntimeError("额度不足，请先兑换邀请码后重试")):
            run_test_job_background("job-456")

        mock_update_job.assert_called_once_with(
            "job-456",
            status=JOB_STATUS_UPLOAD_READY,
            progress=PROGRESS_UPLOAD_READY,
        )

    def test_recover_interrupted_test_runs_promotes_complete_drafts_to_test_ready(self) -> None:
        job_id = "job_recover_ready"
        create_job(job_id, "CREATED", "user-1")
        test_dir = Path(self.tmpdir.name) / "jobs" / job_id / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】a\n", encoding="utf-8")
        (test_dir / "chapters_draft.txt").write_text("【1】A\n", encoding="utf-8")
        update_job(job_id, status="TEST_RUNNING", progress=30, stage_code="TEST_QUEUED", stage_message="running")

        recovered = recover_interrupted_test_runs()

        self.assertEqual(recovered, 1)
        job = get_job(job_id, owner_user_id="user-1")
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "TEST_READY")
        self.assertEqual(job["progress"], 35)


if __name__ == "__main__":
    unittest.main()
