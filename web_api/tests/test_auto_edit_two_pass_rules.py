from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import (
    AutoEdit,
    REMOVE_TOKEN,
    _build_llm_remove_prompt,
)


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


def _sample_segments() -> list[dict[str, object]]:
    # 使用超过20字的文本，避免触发短句合并
    return [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "这是前一句的表达内容，我先说错了一些信息。"},
        {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "这是后一句的表达内容，这是更加准确的表达方式。"},
    ]


class AutoEditTwoPassRulesTest(unittest.TestCase):
    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_cannot_restore_removed_line(self, mock_chat) -> None:
        """Test that _auto_edit_segment_chunk keeps remove markers and doesn't restore removed lines."""
        mock_chat.side_effect = [
            "\n".join(
                [
                    f"[L0001] {REMOVE_TOKEN}",
                    "[L0002] 这是后一句的表达内容，这是更加准确的表达方式。",
                ]
            ),
            # Step 2: LLM tries to restore L1 but it should be ignored
            "\n".join(
                [
                    "[L0001] 我把前句恢复回来。",  # This should be ignored
                    "[L0002] 这是后一句的表达内容，这是更加准确的表达方式！",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segment_chunk(_sample_segments())
        subs = result["optimized_subs"]

        # _auto_edit_segment_chunk returns all lines (merge happens outside in _auto_edit_segments)
        self.assertEqual(len(subs), 2)
        # L1 should keep the remove marker
        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        # L2 should have the optimized content
        self.assertEqual(subs[1].content, "这是后一句的表达内容，这是更加准确的表达方式")

    def test_remove_prompt_requires_drop_earlier_duplicate(self) -> None:
        tagged = (
            "[L0001] [00:00] 前句：重复语义。\n"
            "[L0002] [00:01] 后句：同一语义但更好。"
        )
        messages = _build_llm_remove_prompt(tagged)
        system_prompt = messages[0]["content"]
        self.assertIn("口播", system_prompt)
        self.assertIn("先说错", system_prompt)
        self.assertIn("最后重说一遍", system_prompt)
        self.assertIn("只保留最后那句真正定稿的话", system_prompt)
        self.assertIn("优先删除", system_prompt)
        self.assertIn("同义只留最后一句", system_prompt)

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_low_speech_placeholder_is_always_removed(self, mock_chat) -> None:
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] < Low Speech >",
                    "[L0002] 正常文本，这里应该保留。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] < Low Speech >",
                    "[L0002] 正常文本，这里应该保留。",
                ]
            ),
        ]
        segments = [
            {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "< Low Speech >"},
            {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "正常文本，这里应该保留。"},
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segment_chunk(segments)
        subs = result["optimized_subs"]

        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(subs[1].content, "正常文本，这里应该保留")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_step15_keeps_remove_line_and_blocks_merge(self, mock_chat) -> None:
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 短句一",
                    f"[L0002] {REMOVE_TOKEN}",
                    "[L0003] 短句二",
                    "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 短句一",
                    "[L0002] 这句要删除",
                    "[L0003] 短句二",
                    "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
        ]
        segments = [
            {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "短句一"},
            {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "这句要删除"},
            {"id": 3, "start": 2.4, "end": 3.4, "duration": 1.0, "text": "短句二"},
            {
                "id": 4,
                "start": 3.6,
                "end": 4.6,
                "duration": 1.0,
                "text": "这句很长不需要合并因为已经超过二十字阈值",
            },
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        subs = result["optimized_subs"]

        self.assertEqual(len(subs), 3)
        self.assertEqual(subs[0].content, "短句一")
        self.assertTrue(subs[1].content.startswith(REMOVE_TOKEN))
        self.assertEqual(subs[2].content, "短句二，这句很长不需要合并因为已经超过二十字阈值")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_strips_trailing_punctuation_for_non_question(self, mock_chat) -> None:
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 这是保留句子。",
                    "[L0002] 这也是保留句子！",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 这是保留句子。",
                    "[L0002] 这也是保留句子！",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segment_chunk(
            [
                {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "这是保留句子。"},
                {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "这也是保留句子！"},
            ]
        )

        self.assertEqual(result["optimized_subs"][0].content, "这是保留句子")
        self.assertEqual(result["optimized_subs"][1].content, "这也是保留句子")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_keeps_question_mark(self, mock_chat) -> None:
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 这个功能好用吗？",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 这个功能好用吗？",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segment_chunk(
            [
                {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "这个功能好用吗？"},
            ]
        )

        self.assertEqual(result["optimized_subs"][0].content, "这个功能好用吗？")


if __name__ == "__main__":
    unittest.main()
