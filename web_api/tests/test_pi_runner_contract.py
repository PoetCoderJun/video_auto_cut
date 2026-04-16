from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import TestPiRequest, run_test_pi
from web_api.tests.utils import extract_labeled_path



class TestPiRunnerContractTests(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_delete_contract_requires_all_line_ids(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            self.assertIn("--tools", command)
            self.assertIn("read,write,ls", command)
            prompt = command[-1]
            self.assertIn("只读取上面的输入文件，只写入上面的输出文件", prompt)
            self.assertIn("不要探索仓库", prompt)
            self.assertIn("唯一删除原则", prompt)
            self.assertIn("只要后一句和前一句属于重复语义，必须删除前面的重复部分", prompt)
            output_path = extract_labeled_path(prompt, "输出文件")
            output_path.write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with self.assertRaisesRegex(RuntimeError, "Delete output must cover all input subtitle lines exactly once"):
            run_test_pi(
                TestPiRequest(
                    task="delete",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    segments=[
                        {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                        {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                    ],
                )
            )

    def test_unknown_task_fails_fast(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported Test PI task"):
            run_test_pi(
                TestPiRequest(  # type: ignore[arg-type]
                    task="unknown",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                )
            )

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_delete_contract_tolerates_normalized_no_speech_placeholder(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text(
                "【00:00:00.000-00:00:01.000】<remove><No Speech>\n"
                "【00:00:01.000-00:00:02.000】第二句\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "< No Speech >"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                ],
            )
        )

        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertEqual(artifacts.lines[0]["original_text"], "< No Speech >")

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_delete_contract_keeps_remove_token_out_of_internal_lines(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text(
                "【00:00:00.000-00:00:01.000】<remove>前一句删掉\n"
                "【00:00:01.000-00:00:02.000】第二句\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "前一句删掉"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                ],
            )
        )

        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertNotIn("<remove>", artifacts.lines[0]["original_text"])
        self.assertNotIn("<remove>", artifacts.lines[0]["optimized_text"])

    def test_max_lines_budget_fails_fast_without_chunk_fallback(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exceeds non-chunk budget"):
            run_test_pi(
                TestPiRequest(
                    task="delete",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    segments=[
                        {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                        {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                    ],
                    max_lines=1,
                )
            )


if __name__ == "__main__":
    unittest.main()
