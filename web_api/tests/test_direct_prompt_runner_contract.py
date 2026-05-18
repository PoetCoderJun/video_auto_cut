from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.direct_prompt_runner import TestPromptRequest, run_test_prompt


class DirectPromptRunnerContractTests(unittest.TestCase):
    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_delete_prompt_uses_sparse_index_input(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["role"], "user")
            self.assertIn("只输出需要删除的行号", messages[0]["content"])
            self.assertIn("同一内容连续试讲多次", messages[0]["content"])
            self.assertIn("最接近脚本且完整顺畅", messages[0]["content"])
            self.assertIn("优先用参考口播脚本判断", messages[0]["content"])
            self.assertIn("## 参考口播脚本", messages[0]["content"])
            self.assertIn("参考里的 OpenAI 正确说法", messages[0]["content"])
            self.assertIn("## 待处理字幕", messages[0]["content"])
            self.assertIn("< No Speech >", messages[0]["content"])
            self.assertIn("1\t第一句", messages[0]["content"])
            self.assertIn("2\t第二句", messages[0]["content"])
            return "1\n"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                ],
                script="参考里的 OpenAI 正确说法",
            )
        )
        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertFalse(artifacts.lines[1]["user_final_remove"])

    def test_unknown_task_fails_fast(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported direct prompt task"):
            run_test_prompt(
                TestPromptRequest(  # type: ignore[arg-type]
                    task="unknown",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                )
            )

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_delete_contract_tolerates_normalized_no_speech_placeholder_without_model_delete(self, mock_chat) -> None:
        mock_chat.return_value = ""
        artifacts = run_test_prompt(
            TestPromptRequest(
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

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_delete_locally_predeletes_obvious_filler_without_model_call_when_all_local(self, mock_chat) -> None:
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="delete",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "< No Speech >"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "嗯，"},
                ],
            )
        )

        mock_chat.assert_not_called()
        self.assertEqual([line["line_id"] for line in artifacts.lines], [1, 2])
        self.assertTrue(all(line["user_final_remove"] for line in artifacts.lines))
        self.assertTrue(artifacts.debug["skipped_model"])
        self.assertEqual(artifacts.debug["local_predelete_line_ids"], [1, 2])

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_delete_output_rejects_unknown_line_id(self, mock_chat) -> None:
        mock_chat.return_value = "3\n"
        with self.assertRaisesRegex(RuntimeError, "unknown line ids"):
            run_test_prompt(
                TestPromptRequest(
                    task="delete",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    segments=[
                        {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                        {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                    ],
                )
            )

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_prompt_uses_sparse_changed_rows(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["role"], "user")
            self.assertIn("# polish direct prompt", messages[0]["content"])
            self.assertIn("只输出需要改动的行", messages[0]["content"])
            self.assertIn("ASR 错词、同音误识别、英文/专有名词误识别", messages[0]["content"])
            self.assertIn("不要扩写事实，不要改结论，不要跨行借内容", messages[0]["content"])
            self.assertIn("1\t原句", messages[0]["content"])
            self.assertIn("2\t删掉的原句", messages[0]["content"])
            return "1\t润色后\n2\t删掉的原句也润色\n"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_prompt(
            TestPromptRequest(
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
                    },
                    {
                        "line_id": 2,
                        "start": 130.0,
                        "end": 131.0,
                        "original_text": "删掉的原句",
                        "optimized_text": "删掉的原句",
                        "ai_suggest_remove": True,
                        "user_final_remove": True,
                    },
                ],
            )
        )
        self.assertEqual(artifacts.lines[0]["optimized_text"], "润色后")
        self.assertEqual(artifacts.lines[1]["optimized_text"], "删掉的原句也润色")
        self.assertTrue(artifacts.lines[1]["ai_suggest_remove"])
        self.assertTrue(artifacts.lines[1]["user_final_remove"])

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_contract_allows_empty_marker_for_filler_only_line(self, mock_chat) -> None:
        mock_chat.return_value = "1\t<empty>\n"
        artifacts = run_test_prompt(
            TestPromptRequest(
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

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_contract_treats_embedded_empty_marker_as_remove(self, mock_chat) -> None:
        mock_chat.return_value = "1\t然后<empty>\n"
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "然后", "optimized_text": "然后", "ai_suggest_remove": False, "user_final_remove": False},
                ],
            )
        )
        self.assertTrue(artifacts.lines[0]["user_final_remove"])
        self.assertTrue(artifacts.lines[0]["ai_suggest_remove"])

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_contract_keeps_unchanged_lines_when_sparse_output_empty(self, mock_chat) -> None:
        mock_chat.return_value = ""
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "A", "optimized_text": "A", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 2, "start": 1.0, "end": 2.0, "original_text": "B", "optimized_text": "B", "ai_suggest_remove": False, "user_final_remove": False},
                ],
            )
        )
        self.assertEqual([line["optimized_text"] for line in artifacts.lines], ["A", "B"])

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_output_allows_removed_line_id_without_unremoving_it(self, mock_chat) -> None:
        mock_chat.return_value = "1\t新句子\n"
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "删掉", "optimized_text": "删掉", "ai_suggest_remove": True, "user_final_remove": True},
                ],
            )
        )
        self.assertEqual(artifacts.lines[0]["optimized_text"], "新句子")
        self.assertTrue(artifacts.lines[0]["ai_suggest_remove"])
        self.assertTrue(artifacts.lines[0]["user_final_remove"])

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_polish_ignores_chunking_and_disables_thinking(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertFalse(cfg.get("enable_thinking"))
            content = messages[0]["content"]
            self.assertIn("1\t第一句", content)
            self.assertIn("2\t第二句", content)
            self.assertIn("3\t第三句", content)
            self.assertIn("只输出需要改动的行", content)
            return "1\t第一句优化\n3\t第三句优化\n"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="polish",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k", "enable_thinking": True},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "第一句", "optimized_text": "第一句", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 2, "start": 1.0, "end": 2.0, "original_text": "第二句", "optimized_text": "第二句", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 3, "start": 2.0, "end": 3.0, "original_text": "第三句", "optimized_text": "第三句", "ai_suggest_remove": False, "user_final_remove": False},
                ],
                polish_chunk_size=1,
                polish_concurrency=2,
            )
        )

        self.assertEqual(mock_chat.call_count, 1)
        self.assertEqual([line["optimized_text"] for line in artifacts.lines], ["第一句优化", "第二句", "第三句优化"])
        self.assertNotIn("chunked", artifacts.debug)

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_direct_prompt_cache_reuses_same_prompt_input_and_model(self, mock_chat) -> None:
        mock_chat.return_value = "1\n"
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "video_auto_cut.direct_prompt_runner.DIRECT_PROMPT_CACHE_DIR",
            Path(tmpdir),
        ):
            request = TestPromptRequest(
                task="delete",
                llm_config={
                    "base_url": "http://x",
                    "model": "m",
                    "api_key": "k",
                    "direct_prompt_cache": True,
                },
                segments=[
                    {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                    {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                ],
            )
            first = run_test_prompt(request)
            second = run_test_prompt(request)

        self.assertEqual(mock_chat.call_count, 1)
        self.assertFalse(first.debug["cache_hit"])
        self.assertTrue(second.debug["cache_hit"])
        self.assertTrue(first.lines[0]["user_final_remove"])
        self.assertTrue(second.lines[0]["user_final_remove"])

    def test_max_lines_budget_fails_fast_without_chunk_fallback(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exceeds non-chunk budget"):
            run_test_prompt(
                TestPromptRequest(
                    task="delete",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    segments=[
                        {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                        {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                    ],
                    max_lines=1,
                )
            )

    @patch("video_auto_cut.direct_prompt_runner.llm_utils.chat_completion")
    def test_chapter_prompt_uses_file_prompt_and_strips_code_fences(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            self.assertFalse(cfg.get("enable_thinking"))
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["role"], "user")
            self.assertNotIn("最多只能分成 2 章", messages[0]["content"])
            self.assertNotIn("横屏视频章节约束", messages[0]["content"])
            self.assertNotIn("标题绝不能超过 4 个字", messages[0]["content"])
            self.assertIn("【1】第一段", messages[0]["content"])
            return "```\n【1-2】开场\n```"

        mock_chat.side_effect = fake_chat
        artifacts = run_test_prompt(
            TestPromptRequest(
                task="chapter",
                llm_config={"base_url": "http://x", "model": "m", "api_key": "k", "enable_thinking": True},
                lines=[
                    {"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "第一段", "optimized_text": "第一段", "ai_suggest_remove": False, "user_final_remove": False},
                    {"line_id": 2, "start": 1.0, "end": 2.0, "original_text": "第二段", "optimized_text": "第二段", "ai_suggest_remove": False, "user_final_remove": False},
                ],
                max_chapters=2,
                title_max_chars=5,
                chapter_policy_hint="横屏视频章节约束",
            )
        )
        self.assertEqual(artifacts.chapters[0]["block_range"], "1-2")
        self.assertEqual(artifacts.chapters[0]["title"], "开场")


if __name__ == "__main__":
    unittest.main()
