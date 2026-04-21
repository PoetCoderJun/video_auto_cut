from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import TestPiArtifacts
from video_auto_cut.orchestration.test_cli import _run_cli_test


class TestCliPipelineContractTest(unittest.TestCase):
    @patch("video_auto_cut.orchestration.test_cli._write_highlight_contract")
    @patch("video_auto_cut.orchestration.test_cli.run_test_pi")
    def test_cli_test_runs_delete_then_polish_then_chapter_then_highlight(
        self,
        mock_run_test_pi,
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
                "optimized_text": "后一句polish后表达",
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
                self.assertEqual(request.lines, polish_lines)
                return TestPiArtifacts(
                    task="chapter",
                    lines=polish_lines,
                    chapters=[{"chapter_id": 1, "title": "开场", "block_range": "1"}],
                    debug={"task": "chapter"},
                )
            raise AssertionError(f"unexpected task: {request.task}")

        def fake_highlight_contract(path, *, captions, args):
            order.append("highlight")
            self.assertEqual(captions[0]["text"], "后一句polish后表达")
            Path(path).write_text('{"captions":[]}\n', encoding="utf-8")
            return {"captions": []}

        mock_run_test_pi.side_effect = fake_run_test_pi
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
        self.assertEqual(order, ["delete", "polish", "chapter", "highlight"])


if __name__ == "__main__":
    unittest.main()
