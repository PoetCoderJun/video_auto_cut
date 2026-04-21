from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import main as run_pi_task
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


class PiRunnerEndToEndTests(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_raw_srt_to_final_srt_and_chapters_via_three_task_contracts(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            system_prompt = messages[0]["content"]
            if "delete 阶段执行器" in system_prompt:
                self.assertIn("只输出最终结果文本", messages[1]["content"])
                return (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            if "polish 阶段执行器" in system_prompt:
                self.assertIn("轻微措辞整理", system_prompt)
                return (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            if "chapter 阶段执行器" in system_prompt:
                self.assertIn("连续覆盖全部 block", system_prompt)
                return "【1-2】开场\n"
            raise AssertionError(f"unexpected prompt: {system_prompt}")

        mock_chat.side_effect = fake_chat

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_srt = root / "input.srt"
            delete_txt = root / "delete.txt"
            polish_txt = root / "polish.txt"
            chapters_txt = root / "chapters.txt"
            final_srt = root / "final_test.srt"
            input_srt.write_text(SRT_SAMPLE, encoding="utf-8")

            common = [
                "--llm-base-url",
                "http://localhost:8000",
                "--llm-model",
                "test-model",
            ]
            self.assertEqual(run_pi_task(["--task", "delete", "--input", str(input_srt), "--output", str(delete_txt), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "polish", "--input", str(delete_txt), "--output", str(polish_txt), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "chapter", "--input", str(polish_txt), "--output", str(chapters_txt), *common]), 0)

            lines = build_test_lines_from_text(polish_txt)
            write_final_test_srt(lines, final_srt, "utf-8")
            final_srt_text = final_srt.read_text(encoding="utf-8")
            chapters = build_test_chapters_from_text(chapters_txt, kept_lines=[line for line in lines if not line["user_final_remove"]])

        self.assertIn("<remove>前面这句说错了", final_srt_text)
        self.assertIn("后面这句是正确表达", final_srt_text)
        self.assertIn("再补一句自然一点", final_srt_text)
        self.assertEqual(
            chapters,
            [
                {
                    "chapter_id": 1,
                    "title": "开场",
                    "start": 1.2,
                    "end": 3.4,
                    "block_range": "1-2",
                }
            ],
        )

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_and_chapter_accept_text_line_sidecar(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            system_prompt = messages[0]["content"]
            if "polish 阶段执行器" in system_prompt:
                self.assertIn("`<remove>` 行必须逐字原样保留", system_prompt)
                return (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                )
            if "chapter 阶段执行器" in system_prompt:
                return "【1】开场\n"
            raise AssertionError(f"unexpected prompt: {system_prompt}")

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

            common = [
                "--llm-base-url",
                "http://localhost:8000",
                "--llm-model",
                "test-model",
            ]
            self.assertEqual(run_pi_task(["--task", "polish", "--input", str(delete_txt), "--output", str(polish_output), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "chapter", "--input", str(delete_txt), "--output", str(chapters_output), *common]), 0)

            polished_lines = build_test_lines_from_text(polish_output)
            chapters = build_test_chapters_from_text(
                chapters_output,
                kept_lines=[line for line in polished_lines if not line["user_final_remove"]],
            )

        self.assertEqual([line["line_id"] for line in polished_lines], [1, 2])
        self.assertTrue(polished_lines[0]["user_final_remove"])
        self.assertEqual(
            chapters,
            [{"chapter_id": 1, "title": "开场", "start": 1.2, "end": 2.2, "block_range": "1"}],
        )


if __name__ == "__main__":
    unittest.main()
