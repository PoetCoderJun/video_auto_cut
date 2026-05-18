from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.job_file_repository import list_test_lines, reopen_test_artifacts_for_editing


class JobFileRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
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

    def test_reopen_test_artifacts_copies_confirmed_final_back_to_draft(self) -> None:
        test_dir = Path(self.tmpdir.name) / "jobs" / "job-lines-4" / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        (test_dir / ".confirmed").touch()
        (test_dir / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】old draft\n", encoding="utf-8")
        (test_dir / "final_test.txt").write_text("【00:00:00.000-00:00:01.000】final edit\n", encoding="utf-8")
        (test_dir / "final_chapters.v2.json").write_text(
            json.dumps(
                [
                    {
                        "chapter_key": "chapter-1",
                        "chapter_id": 1,
                        "title": "Final",
                        "start_line_id": 1,
                    }
                ]
            ),
            encoding="utf-8",
        )

        reopened_lines, reopened_chapters = reopen_test_artifacts_for_editing("job-lines-4")
        lines_after_reopen = list_test_lines("job-lines-4")

        self.assertFalse((test_dir / ".confirmed").exists())
        self.assertEqual(reopened_lines[0]["optimized_text"], "final edit")
        self.assertEqual(lines_after_reopen[0]["optimized_text"], "final edit")
        self.assertEqual(reopened_chapters[0]["title"], "Final")


if __name__ == "__main__":
    unittest.main()
