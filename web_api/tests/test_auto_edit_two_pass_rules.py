from __future__ import annotations

import unittest
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


class AutoEditCanonicalRunnerTest(unittest.TestCase):
    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_stage_and_preview_callbacks_follow_delete_then_polish(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            if "delete 阶段执行器" in messages[0]["content"]:
                return "1\n"
            return "2\t这是后一句的表达内容，这是更加准确的表达方式\n"

        mock_chat.side_effect = fake_chat

        stage_events: list[tuple[str, str]] = []
        preview_batches: list[list[dict[str, object]]] = []
        args = DummyArgs()
        args.auto_edit_stage_callback = lambda code, msg: stage_events.append((code, msg))
        args.auto_edit_preview_callback = lambda lines: preview_batches.append(lines)

        result = AutoEdit.from_args(args)._auto_edit_segments(_sample_segments(), total_length=10.0)

        self.assertEqual([code for code, _ in stage_events], ["REMOVING_REDUNDANT_LINES", "POLISHING_EXPRESSION"])
        self.assertEqual(len(preview_batches), 2)
        self.assertTrue(preview_batches[0][0]["ai_suggest_remove"])
        self.assertEqual(preview_batches[1][1]["optimized_text"], "这是后一句的表达内容，这是更加准确的表达方式")
        self.assertEqual(result["optimized_subs"][1].content, "这是后一句的表达内容，这是更加准确的表达方式")

    @patch("video_auto_cut.pi_agent_runner.llm_utils.chat_completion")
    def test_polish_output_rejects_unknown_sparse_line_id(self, mock_chat) -> None:
        def fake_chat(cfg, messages):
            if "delete 阶段执行器" in messages[0]["content"]:
                return ""
            return "3\t第一句润色\n"

        mock_chat.side_effect = fake_chat

        with self.assertRaisesRegex(RuntimeError, "unknown or removed line ids"):
            AutoEdit.from_args(DummyArgs())._auto_edit_segments(_sample_segments(), total_length=10.0)


if __name__ == "__main__":
    unittest.main()
