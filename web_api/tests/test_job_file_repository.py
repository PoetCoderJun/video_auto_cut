from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.job_file_repository import list_test_lines


class JobFileRepositoryTest(unittest.TestCase):
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

    def test_list_test_lines_prefers_draft_until_confirmed(self) -> None:
        test_dir = Path(self.tmpdir.name) / "jobs" / "job-lines-1" / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】draft\n", encoding="utf-8")
        (test_dir / "final_test.txt").write_text("【00:00:00.000-00:00:01.000】final\n", encoding="utf-8")

        lines = list_test_lines("job-lines-1")

        self.assertEqual(lines[0]["optimized_text"], "draft")

    def test_list_test_lines_uses_final_after_confirmed(self) -> None:
        test_dir = Path(self.tmpdir.name) / "jobs" / "job-lines-2" / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / ".confirmed").touch()
        (test_dir / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】draft\n", encoding="utf-8")
        (test_dir / "final_test.txt").write_text("【00:00:00.000-00:00:01.000】final\n", encoding="utf-8")

        lines = list_test_lines("job-lines-2")

        self.assertEqual(lines[0]["optimized_text"], "final")

    def test_list_test_lines_falls_back_to_final_when_draft_is_missing(self) -> None:
        test_dir = Path(self.tmpdir.name) / "jobs" / "job-lines-3" / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / "final_test.txt").write_text("【00:00:00.000-00:00:01.000】final\n", encoding="utf-8")

        lines = list_test_lines("job-lines-3")

        self.assertEqual(lines[0]["optimized_text"], "final")


if __name__ == "__main__":
    unittest.main()
