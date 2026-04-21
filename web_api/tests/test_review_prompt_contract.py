from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import TestPiArtifacts
from video_auto_cut.editing.direct_prompts import build_review_messages
from video_auto_cut.orchestration.test_cli import _build_review_input, _run_cli_test


class ReviewPromptContractTest(unittest.TestCase):
    def test_review_system_prompt_focuses_on_delete_and_polish_main_chain(self) -> None:
        messages = build_review_messages("[原始转写]\nA\n\n[delete+polish 最终稿]\nB")
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]

        self.assertIn("Delete 审核基准：", system_prompt)
        self.assertIn("Polish 审核基准：", system_prompt)
        self.assertIn("只要后一句是前一句更完整、更准确、更最终的重说/补说/纠正版本，就应该删前留后", system_prompt)
        self.assertIn("不能跨行借内容，不能补原文没有的新事实", system_prompt)
        self.assertNotIn("chapter 阶段", system_prompt)
        self.assertNotIn("highlight 阶段", system_prompt)
        self.assertIn("delete+polish 最终稿", user_prompt)

    def test_review_input_only_contains_raw_and_final_sections(self) -> None:
        raw_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "前一句起手残片",
                "optimized_text": "前一句起手残片",
                "user_final_remove": False,
            }
        ]
        final_lines = [
            {
                "line_id": 1,
                "start": 1.0,
                "end": 2.0,
                "original_text": "后一句完整表达",
                "optimized_text": "后一句完整表达",
                "user_final_remove": False,
            }
        ]

        payload = _build_review_input(raw_lines=raw_lines, final_lines=final_lines)

        self.assertIn("[原始转写]", payload)
        self.assertIn("[delete+polish 最终稿]", payload)
        self.assertNotIn("[章节]", payload)
        self.assertNotIn("[高亮]", payload)

    @patch("video_auto_cut.orchestration.test_cli._write_highlight_contract")
    @patch("video_auto_cut.orchestration.test_cli._write_review_report")
    @patch("video_auto_cut.orchestration.test_cli.run_test_pi")
    def test_cli_test_runs_review_after_polish_before_chapter_and_highlight(
        self,
        mock_run_test_pi,
        mock_write_review_report,
        mock_write_highlight_contract,
    ) -> None:
        order: list[str] = []
        delete_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "前一句起手残片",
                "optimized_text": "前一句起手残片",
                "ai_suggest_remove": True,
                "user_final_remove": True,
            },
            {
                "line_id": 2,
                "start": 1.0,
                "end": 2.0,
                "original_text": "后一句完整表达",
                "optimized_text": "后一句完整表达",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]
        polish_lines = [
            {
                "line_id": 2,
                "start": 1.0,
                "end": 2.0,
                "original_text": "后一句完整表达",
                "optimized_text": "后一句最终成片表达",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
        ]

        def fake_run_test_pi(request):
            order.append(request.task)
            if request.task == "delete":
                return TestPiArtifacts(task="delete", lines=delete_lines, debug={"task": "delete"})
            if request.task == "polish":
                return TestPiArtifacts(task="polish", lines=polish_lines, debug={"task": "polish"})
            if request.task == "chapter":
                return TestPiArtifacts(
                    task="chapter",
                    lines=polish_lines,
                    chapters=[{"chapter_id": 1, "title": "开场", "block_range": "1"}],
                    debug={"task": "chapter"},
                )
            raise AssertionError(f"unexpected task: {request.task}")

        def fake_review_report(path, *, raw_lines, final_lines, args):
            order.append("review")
            self.assertEqual(final_lines, polish_lines)
            Path(path).write_text("总评：通过\n", encoding="utf-8")
            return {"path": str(path)}

        def fake_highlight_contract(path, *, captions, args):
            order.append("highlight")
            Path(path).write_text('{"captions":[]}\n', encoding="utf-8")
            return {"captions": []}

        mock_run_test_pi.side_effect = fake_run_test_pi
        mock_write_review_report.side_effect = fake_review_report
        mock_write_highlight_contract.side_effect = fake_highlight_contract

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.srt"
            output_path = Path(tmpdir) / "result.summary.json"
            input_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n前一句起手残片\n\n2\n00:00:01,000 --> 00:00:02,000\n后一句完整表达\n",
                encoding="utf-8",
            )
            args = Namespace(
                task="test",
                input=str(input_path),
                output=str(output_path),
                encoding="utf-8",
                llm_base_url="http://localhost:8000",
                llm_model="test-model",
                llm_api_key="test-key",
                llm_timeout=60,
                llm_max_tokens=None,
                title_max_chars=5,
                max_lines=200,
                lang=None,
                prompt="",
                pi_bin="pi",
                pi_args=[],
            )

            exit_code = _run_cli_test(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(order, ["delete", "polish", "review", "chapter", "highlight"])


if __name__ == "__main__":
    unittest.main()
