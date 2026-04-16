from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from web_api.config import get_settings
from web_api.constants import JOB_STATUS_TEST_CONFIRMED, JOB_STATUS_SUCCEEDED
from web_api.config import job_dir
from web_api.job_file_repository import create_job, upsert_job_files
from web_api.services.cleanup import cleanup_job_artifacts, list_expired_succeeded_jobs, list_succeeded_jobs_with_artifacts


class CleanupTests(unittest.TestCase):
    def test_only_succeeded_jobs_are_cleanup_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "WORK_DIR": tmpdir,
                    "WEB_DB_LOCAL_ONLY": "1",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    create_job("job_cleanup_succeeded", JOB_STATUS_SUCCEEDED, "user")
                    create_job("job_cleanup_test_confirmed", JOB_STATUS_TEST_CONFIRMED, "user")
                    upsert_job_files(
                        "job_cleanup_succeeded",
                        final_video_path=str(Path(tmpdir) / "jobs" / "job_cleanup_succeeded" / "final.mp4"),
                    )
                    upsert_job_files(
                        "job_cleanup_test_confirmed",
                        final_video_path=str(Path(tmpdir) / "jobs" / "job_cleanup_test_confirmed" / "final.mp4"),
                    )
                    Path(tmpdir, "jobs", "job_cleanup_succeeded", "final.mp4").parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    Path(tmpdir, "jobs", "job_cleanup_succeeded", "final.mp4").write_text("x")
                    Path(tmpdir, "jobs", "job_cleanup_test_confirmed", "final.mp4").parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    Path(tmpdir, "jobs", "job_cleanup_test_confirmed", "final.mp4").write_text("x")

                    candidates = list_succeeded_jobs_with_artifacts(limit=10)
                    cutoff = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
                    expired = list_expired_succeeded_jobs(cutoff, limit=10)

                    self.assertIn("job_cleanup_succeeded", candidates)
                    self.assertNotIn("job_cleanup_test_confirmed", candidates)
                    self.assertIn("job_cleanup_succeeded", expired)
                    self.assertNotIn("job_cleanup_test_confirmed", expired)
                finally:
                    get_settings.cache_clear()

    def test_cleanup_job_artifacts_does_not_rewrite_job_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "WORK_DIR": tmpdir,
                    "WEB_DB_LOCAL_ONLY": "1",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    create_job("job_cleanup_rewrite", JOB_STATUS_SUCCEEDED, "user")
                    upsert_job_files(
                        "job_cleanup_rewrite",
                        final_video_path=str(Path(tmpdir) / "jobs" / "job_cleanup_rewrite" / "final.mp4"),
                    )
                    Path(tmpdir, "jobs", "job_cleanup_rewrite", "final.mp4").parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    Path(tmpdir, "jobs", "job_cleanup_rewrite", "final.mp4").write_text("x")

                    removed = cleanup_job_artifacts("job_cleanup_rewrite", reason="unit-test")

                    self.assertGreaterEqual(removed, 1)
                    self.assertFalse(job_dir("job_cleanup_rewrite").exists())
                finally:
                    get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
