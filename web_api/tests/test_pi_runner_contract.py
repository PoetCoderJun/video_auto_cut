from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import TestPiRequest, run_test_pi


class TestPiRunnerContractTests(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_contract_requires_all_line_ids(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertIn("delete 阶段执行器", messages[0]["content"])
            self.assertIn("删前留后", messages[0]["content"])
            self.assertIn("【00:00:00.000-00:00:01.000】第一句", messages[1]["content"])
            return "【00:00:00.000-00:00:01.000】第一句\n"

        mock_chat.side_effect = fake_chat

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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_contract_tolerates_normalized_no_speech_placeholder(self, mock_chat) -> None:
        mock_chat.return_value = (
            "【00:00:00.000-00:00:01.000】<remove><No Speech>\n"
            "【00:00:01.000-00:00:02.000】第二句\n"
        )

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
    def test_delete_contract_keeps_remove_token_out_of_internal_lines(self, mock_chat) -> None:
        mock_chat.return_value = (
            "【00:00:00.000-00:00:01.000】<remove>前一句删掉\n"
            "【00:00:01.000-00:00:02.000】第二句\n"
        )

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
        self.assertEqual(artifacts.debug["runner"]["mode"], "direct-prompt")

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_contract_matches_rendered_millisecond_tags(self, mock_chat) -> None:
        mock_chat.return_value = "【00:00:08.876-00:02:09.676】第一句\n"

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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_delete_contract_tolerates_trailing_punctuation_normalization(self, mock_chat) -> None:
        mock_chat.return_value = "【00:01:09.356-00:01:12.396】而我这个真的是能让在录口播的时候\n"

        artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {
                        "id": 1,
                        "start": 69.356,
                        "end": 72.396,
                        "text": "而我这个真的是能让在录口播的时候，",
                    }
                ],
            )
        )

        self.assertEqual(len(artifacts.lines), 1)
        self.assertFalse(artifacts.lines[0]["user_final_remove"])

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_contract_matches_rendered_millisecond_tags(self, mock_chat) -> None:
        mock_chat.return_value = "【00:00:08.876-00:02:09.676】润色后\n"

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

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_contract_allows_empty_output_for_filler_only_line(self, mock_chat) -> None:
        mock_chat.return_value = "【00:02:14.236-00:02:14.316】\n"

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
