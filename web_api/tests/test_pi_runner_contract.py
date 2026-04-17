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

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_delete_contract_matches_rendered_millisecond_tags(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:08.876-00:02:09.676】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 8.876, "end": 129.6755, "text": "第一句"},
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)
        self.assertAlmostEqual(artifacts.lines[0]["start"], 8.876, places=3)
        self.assertAlmostEqual(artifacts.lines[0]["end"], 129.676, places=3)

    @patch("video_auto_cut.pi_agent_runner.time.sleep")
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_transient_overload_retries_before_succeeding(self, mock_run, mock_sleep) -> None:
        def fake_run(command, **kwargs):
            if mock_run.call_count == 1:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout="",
                    stderr='429 {"error":{"type":"rate_limit_error","message":"The engine is currently overloaded, please try again later"},"type":"error"}',
                )
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={
                    "base_url": "http://x",
                    "model": "m",
                    "api_key": "k",
                    "request_retries": 2,
                    "retry_backoff_seconds": 0,
                },
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)
        self.assertEqual(mock_run.call_count, 2)
        mock_sleep.assert_not_called()

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_polish_contract_matches_rendered_millisecond_tags(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:08.876-00:02:09.676】润色后\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {
                        "line_id": 1,
                        "start": 8.876,
                        "end": 129.6755,
                        "original_text": "原句",
                        "optimized_text": "原句",
                        "ai_suggest_remove": False,
                        "user_final_remove": False,
                    }
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)
        self.assertEqual(artifacts.lines[0]["optimized_text"], "润色后")

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

    @patch.dict("os.environ", {"KIMI_API_KEY": "kimi-secret"}, clear=False)
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_kimi_coding_base_url_routes_pi_to_builtin_provider(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            self.assertIn("--model", command)
            model_index = command.index("--model") + 1
            self.assertEqual(command[model_index], "kimi-coding/k2p5")
            self.assertEqual(kwargs["env"]["KIMI_API_KEY"], "kimi-secret")
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "https://api.kimi.com/coding/v1", "model": "kimi-k2.5", "api_key": "wrong-key"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)

    @patch.dict("os.environ", {"KIMI_API_KEY": "kimi-secret"}, clear=False)
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_kimi_coding_is_default_when_key_exists(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            model_index = command.index("--model") + 1
            self.assertEqual(command[model_index], "kimi-coding/k2p5")
            self.assertEqual(kwargs["env"]["KIMI_API_KEY"], "kimi-secret")
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"model": "kimi-k2.5"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)

    @patch.dict("os.environ", {"KIMI_API_KEY": "", "MOONSHOT_API_KEY": "", "PI_PROVIDER": ""}, clear=False)
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_falls_back_to_vac_llm_when_no_kimi_key_exists(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            model_index = command.index("--model") + 1
            self.assertEqual(command[model_index], "vac-llm/kimi-k2.5")
            output_path = extract_labeled_path(command[-1], "输出文件")
            output_path.write_text("【00:00:00.000-00:00:01.000】第一句\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"model": "kimi-k2.5"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)


if __name__ == "__main__":
    unittest.main()
