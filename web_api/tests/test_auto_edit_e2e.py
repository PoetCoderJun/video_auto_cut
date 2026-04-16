from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import AutoEdit, REMOVE_TOKEN
from web_api.tests.utils import extract_labeled_path


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


def make_segments(texts: list[str]) -> list[dict[str, object]]:
    segments = []
    start = 0.0
    for index, text in enumerate(texts, start=1):
        segments.append(
            {
                "id": index,
                "start": start,
                "end": start + 1.0,
                "duration": 1.0,
                "text": text,
            }
        )
        start += 1.2
    return segments


class AutoEditPiRunnerE2ETest(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_non_chunked_flow_returns_test_lines_and_optimized_subtitles(self, mock_run) -> None:
        segments = make_segments(["前面这句说错了", "后面这句是正确表达", "再补一句自然一点"])

        def fake_run(command, **kwargs):
            prompt = command[-1]
            output_path = extract_labeled_path(prompt, "输出文件")
            if "delete skill" in prompt:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            else:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>前面这句说错了\n"
                    "【00:00:01.200-00:00:02.200】后面这句是正确表达\n"
                    "【00:00:02.400-00:00:03.400】再补一句自然一点\n"
                )
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        result = AutoEdit.from_args(DummyArgs())._auto_edit_segments(segments, total_length=10.0)

        self.assertEqual(len(result["optimized_subs"]), 3)
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertNotIn(REMOVE_TOKEN, result["test_lines"][0]["original_text"])
        self.assertNotIn(REMOVE_TOKEN, result["test_lines"][0]["optimized_text"])
        self.assertEqual(result["optimized_subs"][1].content, "后面这句是正确表达")
        self.assertEqual(result["optimized_subs"][2].content, "再补一句自然一点")
        self.assertEqual(len(result["test_lines"]), 3)
        self.assertTrue(result["test_lines"][0]["ai_suggest_remove"])
        self.assertEqual(result["edl"], [{"start": 1.2, "end": 3.4}])
        self.assertFalse(result["debug"]["default_chunk_first"])
        self.assertEqual(result["debug"]["task_contracts"], ["delete", "polish", "chapter"])

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_low_speech_is_forced_removed(self, mock_run) -> None:
        segments = make_segments(["< Low Speech >", "后面这一句保留"])

        def fake_run(command, **kwargs):
            prompt = command[-1]
            output_path = extract_labeled_path(prompt, "输出文件")
            if "delete skill" in prompt:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>< Low Speech >\n"
                    "【00:00:01.200-00:00:02.200】后面这一句保留\n"
                )
            else:
                output = (
                    "【00:00:00.000-00:00:01.000】<remove>< Low Speech >\n"
                    "【00:00:01.200-00:00:02.200】后面这一句保留\n"
                )
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        result = AutoEdit.from_args(DummyArgs())._auto_edit_segments(segments, total_length=5.0)

        self.assertTrue(result["test_lines"][0]["ai_suggest_remove"])
        self.assertNotIn(REMOVE_TOKEN, result["test_lines"][0]["original_text"])
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(result["optimized_subs"][1].content, "后面这一句保留")
        self.assertEqual(result["edl"], [{"start": 1.2, "end": 2.2}])

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_all_removed_raises_runtime_error(self, mock_run) -> None:
        segments = make_segments(["第一句", "第二句"])

        def fake_run(command, **kwargs):
            prompt = command[-1]
            output_path = extract_labeled_path(prompt, "输出文件")
            output = (
                "【00:00:00.000-00:00:01.000】<remove>第一句\n"
                "【00:00:01.200-00:00:02.200】<remove>第二句\n"
            )
            output_path.write_text(output, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with self.assertRaisesRegex(RuntimeError, "All segments removed"):
            AutoEdit.from_args(DummyArgs())._auto_edit_segments(segments, total_length=5.0)

    @patch("video_auto_cut.pi_agent_runner.subprocess.run")
    def test_invalid_delete_output_fails_fast_without_repair_prompt(self, mock_run) -> None:
        segments = make_segments(["第一句", "第二句"])

        def fake_run(command, **kwargs):
            prompt = command[-1]
            output_path = extract_labeled_path(prompt, "输出文件")
            output_path.write_text("not valid output\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

        mock_run.side_effect = fake_run

        with self.assertRaisesRegex(RuntimeError, "Invalid timed line format"):
            AutoEdit.from_args(DummyArgs())._auto_edit_segments(segments, total_length=5.0)


if __name__ == "__main__":
    unittest.main()
