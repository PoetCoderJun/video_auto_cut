from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import TestPiRequest, run_test_pi


class TestPiRunnerContractTests(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_prompt_uses_sparse_index_input(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertIn("只输出需要删除的行号", messages[0]["content"])
            self.assertIn("1\t第一句", messages[1]["content"])
            self.assertIn("2\t第二句", messages[1]["content"])
            return "1\n"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                ],
            )
        )
        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertFalse(artifacts.lines[1]["user_final_remove"])

    def test_unknown_task_fails_fast(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported Test PI task"):
            run_test_pi(
                TestPiRequest(  # type: ignore[arg-type]
                    task="unknown",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                )
            )

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_contract_tolerates_normalized_no_speech_placeholder_without_model_delete(self, mock_chat) -> None:
        mock_chat.return_value = ""
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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_output_rejects_unknown_line_id(self, mock_chat) -> None:
        mock_chat.return_value = "3\n"
        with self.assertRaisesRegex(RuntimeError, "unknown line ids"):
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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_prompt_uses_sparse_changed_rows(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertIn("只输出那些“需要改写”的行", messages[0]["content"])
            self.assertIn("1\t原句", messages[1]["content"])
            return "1\t润色后\n"

        mock_chat.side_effect = fake_chat
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
        self.assertEqual(artifacts.lines[0]["optimized_text"], "润色后")

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_contract_allows_empty_marker_for_filler_only_line(self, mock_chat) -> None:
        mock_chat.return_value = "1\t<empty>\n"
        artifacts = run_test_pi(
            TestPiRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {
                        "line_id": 1,
                        "start": 134.236,
                        "end": 134.316,
                        "original_text": "嗯，",
                        "optimized_text": "嗯，",
                        "ai_suggest_remove": False,
                        "user_final_remove": False,
                    }
                ],
            )
        )
        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertTrue(artifacts.lines[0]["ai_suggest_remove"])

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_contract_keeps_unchanged_lines_when_sparse_output_empty(self, mock_chat) -> None:
        mock_chat.return_value = ""
        artifacts = run_test_pi(
            TestPiRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "A", "optimized_text": "A", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 2, "start": 1.0, "end": 2.0, "original_text": "B", "optimized_text": "B", "ai_suggest_remove": False, "user_final_remove": False},
                ],
            )
        )
        self.assertEqual([line["optimized_text"] for line in artifacts.lines], ["A", "B"])

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_output_rejects_removed_line_id(self, mock_chat) -> None:
        mock_chat.return_value = "1\t新句子\n"
        with self.assertRaisesRegex(RuntimeError, "unknown or removed line ids"):
            run_test_pi(
                TestPiRequest(
                    task="polish",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    lines=[
                        {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "删掉", "optimized_text": "删掉", "ai_suggest_remove": True, "user_final_remove": True},
                    ],
                )
            )

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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_chapter_prompt_includes_policy_and_strips_code_fences(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertIn("最多只能分成 2 章", messages[0]["content"])
            self.assertIn("横屏视频章节约束", messages[0]["content"])
            self.assertIn("【1】第一段", messages[1]["content"])
            return "```\n【1-2】开场\n```"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_pi(
            TestPiRequest(
                task="chapter",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "第一段", "optimized_text": "第一段", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 2, "start": 1.0, "end": 2.0, "original_text": "第二段", "optimized_text": "第二段", "ai_suggest_remove": False, "user_final_remove": False},
                ],
                max_chapters=2,
                chapter_policy_hint="横屏视频章节约束",
            )
        )
        self.assertEqual(artifacts.chapters[0]["block_range"], "1-2")
        self.assertEqual(artifacts.chapters[0]["title"], "开场")


if __name__ == "__main__":
    unittest.main()
