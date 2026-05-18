from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.direct_prompt_runner import main as run_direct_prompt_task
from video_auto_cut.shared.test_text_io import (
    build_test_chapters_from_text,
    build_test_lines_from_text,
    write_final_test_srt,
)


SRT_SAMPLE = """1
00:00:00,000 --> 00:00:01,000
前面这句说错了

2
00:00:01,200 --> 00:00:02,200
后面这句是正确表达

3
00:00:02,400 --> 00:00:03,400
再补一句自然一点
"""


class DirectPromptRunnerEndToEndTests(unittest.TestCase):
    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_raw_srt_to_final_srt_and_chapters_via_three_task_contracts(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            user_prompt = messages[0]["content"]
            self.assertEqual(messages[0]["role"], "user")
            if "只输出需要删除的行号" in user_prompt:
                self.assertIn("只输出需要删除的行号", user_prompt)
                return "1\n"
            if "只输出需要改动的行" in user_prompt:
                self.assertIn("只输出需要改动的行", user_prompt)
                return ""
            if "章节文本" in user_prompt:
                self.assertIn("连续覆盖全部 block", user_prompt)
                return "【1-2】开场\n"
            raise AssertionError(f"unexpected prompt: {user_prompt}")

        mock_chat.side_effect = fake_chat

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_srt = root / "input.srt"
            delete_txt = root / "delete.txt"
            polish_txt = root / "polish.txt"
            chapters_txt = root / "chapters.txt"
            final_srt = root / "final_test.srt"
            input_srt.write_text(SRT_SAMPLE, encoding="utf-8")

            common = ["--llm-base-url", "http://localhost:8000", "--llm-model", "test-model"]
            self.assertEqual(run_direct_prompt_task(["--task", "delete", "--input", str(input_srt), "--output", str(delete_txt), *common]), 0)
            self.assertEqual(run_direct_prompt_task(["--task", "polish", "--input", str(delete_txt), "--output", str(polish_txt), *common]), 0)
            self.assertEqual(run_direct_prompt_task(["--task", "chapter", "--input", str(polish_txt), "--output", str(chapters_txt), *common]), 0)

            lines = build_test_lines_from_text(polish_txt)
            write_final_test_srt(lines, final_srt, "utf-8")
            final_srt_text = final_srt.read_text(encoding="utf-8")
            chapters = build_test_chapters_from_text(chapters_txt, kept_lines=[line for line in lines if not line["user_final_remove"]])

        self.assertIn("<remove>前面这句说错了", final_srt_text)
        self.assertIn("后面这句是正确表达", final_srt_text)
        self.assertIn("再补一句自然一点", final_srt_text)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_id"], 1)
        self.assertEqual(chapters[0]["title"], "开场")
        self.assertEqual(chapters[0]["start"], 1.2)
        self.assertEqual(chapters[0]["end"], 3.4)
        self.assertEqual(chapters[0]["block_range"], "1-2")
        self.assertEqual(chapters[0]["start_line_id"], 2)
        self.assertTrue(str(chapters[0]["chapter_key"]).startswith("chapter-"))

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_and_chapter_accept_text_line_sidecar(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            user_prompt = messages[0]["content"]
            self.assertEqual(messages[0]["role"], "user")
            if "只输出需要改动的行" in user_prompt:
                return ""
            if "章节文本" in user_prompt:
                return "【1】开场\n"
            raise AssertionError(f"unexpected prompt: {user_prompt}")

        mock_chat.side_effect = fake_chat

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            delete_txt = root / "delete.txt"
            polish_output = root / "polish.txt"
            chapters_output = root / "chapters.txt"
            delete_txt.write_text(
                "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                "【00:00:01.200-00:00:02.200】后面这句是正确表达\n",
                encoding="utf-8",
            )

            common = ["--llm-base-url", "http://localhost:8000", "--llm-model", "test-model"]
            self.assertEqual(run_direct_prompt_task(["--task", "polish", "--input", str(delete_txt), "--output", str(polish_output), *common]), 0)
            self.assertEqual(run_direct_prompt_task(["--task", "chapter", "--input", str(polish_txt := delete_txt), "--output", str(chapters_output), *common]), 0)

            polished_lines = build_test_lines_from_text(polish_output)
            chapters = build_test_chapters_from_text(chapters_output, kept_lines=[line for line in polished_lines if not line["user_final_remove"]])

        self.assertEqual([line["line_id"] for line in polished_lines], [1, 2])
        self.assertTrue(polished_lines[0]["user_final_remove"])
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_id"], 1)
        self.assertEqual(chapters[0]["title"], "开场")
        self.assertEqual(chapters[0]["start"], 1.2)
        self.assertEqual(chapters[0]["end"], 2.2)
        self.assertEqual(chapters[0]["block_range"], "1")
        self.assertEqual(chapters[0]["start_line_id"], 2)
        self.assertTrue(str(chapters[0]["chapter_key"]).startswith("chapter-"))


if __name__ == "__main__":
    unittest.main()
