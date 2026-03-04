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
    return [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "前句：我先说错了。"},
        {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "后句：这是更准确的表达。"},
    ]


class AutoEditTwoPassRulesTest(unittest.TestCase):
    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_cannot_restore_removed_line(self, mock_chat) -> None:
        mock_chat.side_effect = [
            "\n".join(
                [
                    f"[L0001] {REMOVE_TOKEN}",
                    "[L0002] 后句：这是更准确的表达。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 我把前句恢复回来。",
                    "[L0002] 后句：这是更准确的表达！",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segment_chunk(_sample_segments())
        subs = result["optimized_subs"]

        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertIn("前句：我先说错了。", subs[0].content)
        self.assertEqual(subs[1].content, "后句：这是更准确的表达！")

    def test_remove_prompt_requires_drop_earlier_duplicate(self) -> None:
        tagged = (
            "[L0001] [00:00] 前句：重复语义。\n"
            "[L0002] [00:01] 后句：同一语义但更好。"
        )
        messages = _build_llm_remove_prompt(tagged)
        system_prompt = messages[0]["content"]
        self.assertIn("一律删除前面版本", system_prompt)
        self.assertIn("只保留最后出现", system_prompt)
        self.assertIn("仅依据时间先后顺序决定保留对象", system_prompt)
        self.assertIn("禁止使用“更正、补全、完整、通顺、准确”", system_prompt)
        self.assertIn("以下示例必须严格模仿", system_prompt)
        self.assertIn("示例1（同义重复，保留后句）", system_prompt)
        self.assertIn("示例2（前短后长，保留后句）", system_prompt)


if __name__ == "__main__":
    unittest.main()
