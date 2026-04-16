from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import AutoEdit


class DummyArgs:
    def __init__(self) -> None:
        self.inputs = []
        self.encoding = "utf-8"
        self.force = False
        self.auto_edit_llm = True
        self.auto_edit_merge_gap = 0.5
        self.auto_edit_pad_head = 0.0
        self.auto_edit_pad_tail = 0.0
        self.auto_edit_topics = False
        self.topic_strict = False
        self.topic_output = None
        self.llm_base_url = "http://localhost:8000"
        self.llm_model = "test-model"
        self.llm_api_key = None
        self.llm_timeout = 60
        self.llm_temperature = 0.0
        self.llm_max_tokens = None
        self.auto_edit_llm_concurrency = 1


def _sample_segments() -> list[dict[str, object]]:
    return [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "这是前一句的表达内容，我先说错了一些信息。"},
        {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "这是后一句的表达内容，这是更加准确的表达方式。"},
    ]


def _extract_path(prompt: str, label: str) -> Path:
    match = re.search(rf"{label}: (.+)", prompt)
    if not match:
        raise AssertionError(f"missing {label} in prompt: {prompt}")
    return Path(match.group(1).strip())


class AutoEditCanonicalRunnerTest(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_stage_and_preview_callbacks_follow_delete_then_polish(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            prompt = command[-1]
            input_path = _extract_path(prompt, "输入文件")
            output_path = _extract_path(prompt, "输出文件")
            if "delete skill" in prompt:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>这是前一句的表达内容，我先说错了一些信息。\n"
                    "【00:00:01.200-00:00:02.200】这是后一句的表达内容，这是更加准确的表达方式。\n"
                )
            else:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>这是前一句的表达内容，我先说错了一些信息。\n"
                    "【00:00:01.200-00:00:02.200】这是后一句的表达内容，这是更加准确的表达方式\n"
                )
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        stage_events: list[tuple[str, str]] = []
        preview_batches: list[list[dict[str, object]]] = []
        args = DummyArgs()
        args.auto_edit_stage_callback = lambda code, msg: stage_events.append((code, msg))
        args.auto_edit_preview_callback = lambda lines: preview_batches.append(lines)

        result = AutoEdit(args)._auto_edit_segments(_sample_segments(), total_length=10.0)

        self.assertEqual([code for code, _ in stage_events], ["REMOVING_REDUNDANT_LINES", "POLISHING_EXPRESSION"])
        self.assertEqual(len(preview_batches), 2)
        self.assertTrue(preview_batches[0][0]["ai_suggest_remove"])
        self.assertEqual(preview_batches[1][1]["optimized_text"], "这是后一句的表达内容，这是更加准确的表达方式")
        self.assertEqual(result["optimized_subs"][1].content, "这是后一句的表达内容，这是更加准确的表达方式")

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_polish_output_must_cover_all_kept_lines(self, mock_run) -> None:
        def fake_run(command, **kwargs):
            prompt = command[-1]
            input_path = _extract_path(prompt, "输入文件")
            output_path = _extract_path(prompt, "输出文件")
            if "delete skill" in prompt:
                output = (
                    "【00:00:00.000-00:00:01.000】这是前一句的表达内容，我先说错了一些信息。\n"
                    "【00:00:01.200-00:00:02.200】这是后一句的表达内容，这是更加准确的表达方式。\n"
                )
            else:
                output = "【00:00:00.000-00:00:01.000】第一句润色\n"
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with self.assertRaisesRegex(RuntimeError, "Polish output must cover all input subtitle lines exactly once"):
            AutoEdit(DummyArgs())._auto_edit_segments(_sample_segments(), total_length=10.0)


if __name__ == "__main__":
    unittest.main()
