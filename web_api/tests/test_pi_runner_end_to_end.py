from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import main as run_pi_task
from web_api.utils.srt_utils import build_test_chapters_from_text, build_test_lines_from_text, write_final_test_srt


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


def _extract_path(prompt: str, label: str) -> Path:
    match = re.search(rf"{label}: (.+)", prompt)
    if not match:
        raise AssertionError(f"missing {label} in prompt: {prompt}")
    return Path(match.group(1).strip())

class PiRunnerEndToEndTests(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_raw_srt_to_final_srt_and_chapters_via_three_task_contracts(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            self.assertIn("--tools", command)
            self.assertIn("read,write,ls", command)
            prompt = command[-1]
            output_path = _extract_path(prompt, "输出文件")

            if "delete skill" in prompt:
                self.assertIn("不要探索仓库", prompt)
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            elif "polish skill" in prompt:
                self.assertIn("不要探索仓库", prompt)
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            elif "chapter skill" in prompt:
                self.assertIn("所有 block_range 必须连续覆盖全部 block", prompt)
                output = "【1-2】开场\n"
            else:
                raise AssertionError(f"unexpected prompt: {prompt}")

            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_srt = root / "input.srt"
            delete_json = root / "delete.json"
            polish_json = root / "polish.json"
            chapters_json = root / "chapters.json"
            final_srt = root / "final_test.srt"
            input_srt.write_text(SRT_SAMPLE, encoding="utf-8")

            common = [
                "--llm-base-url",
                "http://localhost:8000",
                "--llm-model",
                "test-model",
            ]
            self.assertEqual(run_pi_task(["--task", "delete", "--input", str(input_srt), "--output", str(delete_json), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "polish", "--input", str(delete_json), "--output", str(polish_json), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "chapter", "--input", str(polish_json), "--output", str(chapters_json), *common]), 0)

            lines = build_test_lines_from_text(polish_json)
            write_final_test_srt(lines, final_srt, "utf-8")
            final_srt_text = final_srt.read_text(encoding="utf-8")
            chapters = build_test_chapters_from_text(chapters_json, kept_lines=[line for line in lines if not line["user_final_remove"]])

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

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_polish_and_chapter_accept_json_line_sidecar(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            prompt = command[-1]
            output_path = _extract_path(prompt, "输出文件")
            if "polish skill" in prompt:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                )
            elif "chapter skill" in prompt:
                output = "【1】开场\n"
            else:
                raise AssertionError(f"unexpected prompt: {prompt}")
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            delete_json = root / "delete.json"
            polish_output = root / "polish.txt"
            chapters_output = root / "chapters.txt"
            delete_json.write_text(
                json.dumps(
                    {
                        "lines": [
                            {
                                "line_id": 2,
                                "start": 1.2,
                                "end": 2.2,
                                "original_text": "后面这句是正确表达",
                                "optimized_text": "后面这句是正确表达",
                                "ai_suggest_remove": False,
                                "user_final_remove": False,
                            },
                            {
                                "line_id": 1,
                                "start": 0.0,
                                "end": 1.0,
                                "original_text": "前面这句说错了",
                                "optimized_text": "前面这句说错了",
                                "ai_suggest_remove": True,
                                "user_final_remove": True,
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            common = [
                "--llm-base-url",
                "http://localhost:8000",
                "--llm-model",
                "test-model",
            ]
            self.assertEqual(run_pi_task(["--task", "polish", "--input", str(delete_json), "--output", str(polish_output), *common]), 0)
            self.assertEqual(run_pi_task(["--task", "chapter", "--input", str(delete_json), "--output", str(chapters_output), *common]), 0)

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
