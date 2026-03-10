from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import AUTO_EDIT_CHUNK_LINES, AutoEdit, REMOVE_TOKEN


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


def remove_payload(actions: list[tuple[int, str, str, float]]) -> str:
    return json.dumps(
        {
            "decisions": [
                {
                    "line_id": line_id,
                    "action": action,
                    "edited_text": "",
                    "reason": reason,
                    "confidence": confidence,
                }
                for line_id, action, reason, confidence in actions
            ]
        },
        ensure_ascii=False,
    )


def remove_payload_with_text(
    actions: list[tuple[int, str, str, str, float]]
) -> str:
    return json.dumps(
        {
            "decisions": [
                {
                    "line_id": line_id,
                    "action": action,
                    "edited_text": edited_text,
                    "reason": reason,
                    "confidence": confidence,
                }
                for line_id, action, edited_text, reason, confidence in actions
            ]
        },
        ensure_ascii=False,
    )


def critique_payload(needs_revision: bool, issues: list[dict[str, object]] | None = None) -> str:
    return json.dumps(
        {
            "needs_revision": needs_revision,
            "issues": issues or [],
        },
        ensure_ascii=False,
    )


def polish_payload(lines: list[tuple[int, str, str, float]]) -> str:
    return json.dumps(
        {
            "lines": [
                {
                    "line_id": line_id,
                    "text": text,
                    "reason": reason,
                    "confidence": confidence,
                }
                for line_id, text, reason, confidence in lines
            ]
        },
        ensure_ascii=False,
    )


def rewrite_payload(chunks: list[tuple[int, str, str, float]]) -> str:
    return json.dumps(
        {
            "chunks": [
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "reason": reason,
                    "confidence": confidence,
                }
                for chunk_id, text, reason, confidence in chunks
            ]
        },
        ensure_ascii=False,
    )


class AutoEditPiAgentE2ETest(unittest.TestCase):
    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_non_chunked_flow_returns_step1_lines_and_polished_groups(self, mock_chat) -> None:
        segments = make_segments(
            [
                "前面这句说错了",
                "后面这句是正确表达",
                "短句",
                "继续短",
                "这句很长不需要合并因为已经超过二十字阈值",
            ]
        )
        mock_chat.side_effect = [
            remove_payload_with_text(
                [
                    (1, "REMOVE", "", "被后句覆盖", 0.95),
                    (2, "KEEP", "后面这句是正确表达", "最终版本", 0.92),
                    (3, "KEEP", "短句", "保留", 0.90),
                    (4, "KEEP", "继续短", "保留", 0.90),
                    (5, "KEEP", "这句很长不需要合并因为已经超过二十字阈值", "保留", 0.90),
                ]
            ),
            rewrite_payload(
                [
                    (
                        2,
                        "后面这句是正确表达，短句继续展开，这句很长不需要合并因为已经超过二十字阈值",
                        "整段重写",
                        0.94,
                    ),
                ]
            ),
            critique_payload(False),
        ]

        result = AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=10.0)

        self.assertEqual(len(result["optimized_subs"]), 2)
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(
            result["optimized_subs"][1].content,
            "后面这句是正确表达，短句继续展开，这句很长不需要合并因为已经超过二十字阈值",
        )
        self.assertEqual(len(result["raw_optimized_subs"]), 5)
        self.assertEqual(len(result["step1_lines"]), 2)
        self.assertTrue(result["step1_lines"][0]["ai_suggest_remove"])
        self.assertFalse(result["step1_lines"][1]["ai_suggest_remove"])
        self.assertTrue(result["debug"]["pi_agent"])
        self.assertEqual(result["debug"]["merged_groups"][0]["source_line_ids"], [2, 3, 4, 5])
        self.assertEqual(
            result["debug"]["rewritten_groups"][0]["text"],
            "后面这句是正确表达，短句继续展开，这句很长不需要合并因为已经超过二十字阈值",
        )

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_low_speech_is_forced_removed_in_step1_sidecar(self, mock_chat) -> None:
        segments = make_segments(
            [
                "< Low Speech >",
                "短句一",
                "这句很长不需要合并因为已经超过二十字阈值",
            ]
        )
        mock_chat.side_effect = [
            remove_payload_with_text(
                [
                    (1, "KEEP", "< Low Speech >", "模型漏删", 0.40),
                    (2, "KEEP", "短句一", "保留", 0.90),
                    (3, "KEEP", "这句很长不需要合并因为已经超过二十字阈值", "保留", 0.90),
                ]
            ),
            rewrite_payload(
                [
                    (2, "短句一，这句很长不需要合并因为已经超过二十字阈值", "整段重写", 0.93),
                ]
            ),
            critique_payload(False),
        ]

        result = AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=10.0)

        self.assertTrue(result["step1_lines"][0]["ai_suggest_remove"])
        self.assertEqual(len(result["optimized_subs"]), 2)
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(
            result["optimized_subs"][1].content,
            "短句一，这句很长不需要合并因为已经超过二十字阈值",
        )
        self.assertEqual(len(result["raw_optimized_subs"]), 3)
        self.assertEqual(result["raw_optimized_subs"][1].content, "短句一")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_chunked_flow_runs_boundary_review_and_global_polish(self, mock_chat) -> None:
        total_lines = AUTO_EDIT_CHUNK_LINES + 10
        segments = make_segments(
            [
                "前句试探" if index % 2 == 0 else "这句很长不需要合并因为已经超过二十字阈值"
                for index in range(total_lines)
            ]
        )
        first_chunk_actions = []
        for line_id in range(1, 35):
            action = "REMOVE" if line_id % 2 == 1 else "KEEP"
            text = "前句试探" if line_id % 2 == 1 else "这句很长不需要合并因为已经超过二十字阈值"
            first_chunk_actions.append((line_id, action, text if action == "KEEP" else "", "chunk1", 0.9))
        second_chunk_actions = []
        for line_id in range(27, 41):
            action = "REMOVE" if line_id % 2 == 1 else "KEEP"
            text = "前句试探" if line_id % 2 == 1 else "这句很长不需要合并因为已经超过二十字阈值"
            second_chunk_actions.append((line_id, action, text if action == "KEEP" else "", "chunk2", 0.9))
        kept_even_ids = [line_id for line_id in range(1, total_lines + 1) if line_id % 2 == 0]
        rewritten_chunks = [
            (line_id, "这句很长不需要合并因为已经超过二十字阈值", "整段重写", 0.95)
            for line_id in kept_even_ids
        ]
        mock_chat.side_effect = [
            remove_payload_with_text(first_chunk_actions),
            remove_payload_with_text(second_chunk_actions),
            json.dumps(
                {
                    "dropped_line_ids": [29],
                    "reason": "后一个 chunk 的 overlap 更可信",
                },
                ensure_ascii=False,
            ),
            rewrite_payload(rewritten_chunks),
            critique_payload(False),
        ]

        result = AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=50.0)

        self.assertEqual(len(result["optimized_subs"]), total_lines - 1)
        self.assertTrue(result["debug"]["chunked"])
        self.assertEqual(result["debug"]["chunk_count"], 2)
        self.assertTrue(result["optimized_subs"][0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(result["optimized_subs"][1].content, "这句很长不需要合并因为已经超过二十字阈值")
        self.assertEqual(len(result["step1_lines"]), total_lines - 1)
        self.assertTrue(result["step1_lines"][0]["ai_suggest_remove"])
        self.assertFalse(result["step1_lines"][1]["ai_suggest_remove"])

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_all_removed_raises_runtime_error(self, mock_chat) -> None:
        segments = make_segments(["这句要删除", "这句也要删除"])
        mock_chat.side_effect = [
            remove_payload_with_text(
                [
                    (1, "REMOVE", "", "删除", 0.95),
                    (2, "REMOVE", "", "删除", 0.95),
                ]
            ),
            critique_payload(False),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            AutoEdit(DummyArgs())._auto_edit_segments(segments, total_length=5.0)

        self.assertIn("All segments removed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
