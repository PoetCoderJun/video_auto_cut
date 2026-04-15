from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import AutoEdit, REMOVE_TOKEN


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
    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_non_chunked_flow_returns_step1_lines_and_optimized_subtitles(self, mock_chat) -> None:
        segments = make_segments(
            [
                "前面这句说错了",
                "后面这句是正确表达",
                "再补一句自然一点",
            ]
        )
        mock_chat.side_effect = [
            json.dumps(
                {
                    "lines": [
                        {"line_id": 1, "action": "REMOVE", "reason": "被后文覆盖"},
                        {"line_id": 2, "action": "KEEP", "reason": "保留"},
                        {"line_id": 3, "action": "KEEP", "reason": "保留"},
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "lines": [
                        {"line_id": 2, "text": "后面这句是正确表达", "reason": "润色"},
                        {"line_id": 3, "text": "再补一句自然一点", "reason": "润色"},
                    ]
                },
                ensure_ascii=False,
            ),
        ]

        result = AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=10.0)

        self.assertEqual(len(result["optimized_subs"]), 3)
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(result["optimized_subs"][1].content, "后面这句是正确表达")
        self.assertEqual(result["optimized_subs"][2].content, "再补一句自然一点")
        self.assertEqual(len(result["step1_lines"]), 3)
        self.assertTrue(result["step1_lines"][0]["ai_suggest_remove"])
        self.assertFalse(result["debug"]["default_chunk_first"])
        self.assertEqual(result["debug"]["task_contracts"], ["delete", "polish", "chapter"])

    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_low_speech_is_forced_removed(self, mock_chat) -> None:
        segments = make_segments([
            "< Low Speech >",
            "后面这一句保留",
        ])
        mock_chat.side_effect = [
            json.dumps(
                {
                    "lines": [
                        {"line_id": 1, "action": "KEEP", "reason": "模型漏删"},
                        {"line_id": 2, "action": "KEEP", "reason": "保留"},
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "lines": [
                        {"line_id": 2, "text": "后面这一句保留", "reason": "润色"},
                    ]
                },
                ensure_ascii=False,
            ),
        ]

        result = AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=5.0)

        self.assertTrue(result["step1_lines"][0]["ai_suggest_remove"])
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(result["optimized_subs"][1].content, "后面这一句保留")

    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_all_removed_raises_runtime_error(self, mock_chat) -> None:
        segments = make_segments(["第一句", "第二句"])
        mock_chat.return_value = json.dumps(
            {
                "lines": [
                    {"line_id": 1, "action": "REMOVE", "reason": "删除"},
                    {"line_id": 2, "action": "REMOVE", "reason": "删除"},
                ]
            },
            ensure_ascii=False,
        )

        with self.assertRaisesRegex(RuntimeError, "All segments removed"):
            AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=5.0)

    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_invalid_delete_output_fails_fast_without_repair_prompt(self, mock_chat) -> None:
        segments = make_segments(["第一句", "第二句"])
        mock_chat.return_value = json.dumps(
            {
                "decisions": [
                    {"line_id": 1, "action": "KEEP", "reason": "旧格式"},
                    {"line_id": 2, "action": "KEEP", "reason": "旧格式"},
                ]
            },
            ensure_ascii=False,
        )

        with self.assertRaisesRegex(RuntimeError, "delete output missing lines array"):
            AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=5.0)


if __name__ == "__main__":
    unittest.main()
