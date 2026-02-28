import unittest
from unittest.mock import patch

from autocut.auto_edit import AutoEdit, REMOVE_TOKEN


class DummyArgs:
    def __init__(self):
        self.inputs = []
        self.encoding = "utf-8"
        self.force = False
        self.auto_edit_llm = True
        self.auto_edit_merge_gap = 0.5
        self.auto_edit_pad_head = 0.0
        self.auto_edit_pad_tail = 0.0
        self.llm_base_url = "http://localhost:8000"
        self.llm_model = "test-model"
        self.llm_api_key = None
        self.llm_timeout = 60
        self.llm_temperature = 0.2
        self.llm_max_tokens = None


def _sample_segments():
    return [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "前面这句表达了一个意思。"},
        {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0, "text": "后面把同一个意思说得更准确。"},
        {"id": 3, "start": 2.4, "end": 3.4, "duration": 1.0, "text": "最后补充一个新的信息点。"},
    ]


class TestAutoEditTwoPass(unittest.TestCase):
    @patch("autocut.auto_edit.llm_utils.chat_completion")
    def test_two_pass_flow_remove_then_optimize(self, mock_chat):
        mock_chat.side_effect = [
            "\n".join(
                [
                    f"[L0001] {REMOVE_TOKEN}",
                    "[L0002] 后面把同一个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点。",
                ]
            ),
            "\n".join(
                [
                    f"[L0001] {REMOVE_TOKEN}",
                    "[L0002] 后一句把这个意思说得更准确。",
                    "[L0003] 最后补充一个新信息点并说明。",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(_sample_segments(), total_length=4.0)

        self.assertEqual(mock_chat.call_count, 2)

        first_messages = mock_chat.call_args_list[0].args[1]
        second_messages = mock_chat.call_args_list[1].args[1]
        self.assertIn("任务：只判断每行是否删除", first_messages[0]["content"])
        self.assertIn("只保留最后一个完整且正确的表达", first_messages[0]["content"])
        self.assertIn("第二步任务", second_messages[0]["content"])
        self.assertIn(f"[L0001] {REMOVE_TOKEN}", second_messages[1]["content"])

        subs = result["optimized_subs"]
        self.assertEqual(len(subs), 3)
        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(subs[1].content, "后一句把这个意思说得更准确。")
        self.assertEqual(subs[2].content, "最后补充一个新信息点并说明。")

    @patch("autocut.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_cannot_recover_removed_line(self, mock_chat):
        mock_chat.side_effect = [
            "\n".join(
                [
                    f"[L0001] {REMOVE_TOKEN}",
                    "[L0002] 后面把同一个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 我想把这句恢复回来。",
                    "[L0002] 后一句把这个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点，确保逻辑完整。",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(_sample_segments(), total_length=4.0)
        subs = result["optimized_subs"]

        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertIn("前面这句表达了一个意思。", subs[0].content)

    @patch("autocut.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_cannot_add_new_remove(self, mock_chat):
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 前面这句表达了一个意思。",
                    "[L0002] 后面把同一个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 前一句表达了一个核心意思。",
                    f"[L0002] {REMOVE_TOKEN}",
                    "[L0003] 最后补充一个新的信息点，确保逻辑完整。",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        segments = _sample_segments()
        result = editor._auto_edit_segments(segments, total_length=4.0)
        subs = result["optimized_subs"]

        self.assertEqual(subs[1].content, segments[1]["text"])
        self.assertFalse(subs[1].content.startswith(REMOVE_TOKEN))

    @patch("autocut.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_missing_tags_fallback_to_original(self, mock_chat):
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 前面这句表达了一个意思。",
                    "[L0002] 后面把同一个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 前一句表达了一个核心意思。",
                    "[L0002] 后一句把这个意思说得更准确。",
                    # L0003 intentionally missing
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        segments = _sample_segments()
        result = editor._auto_edit_segments(segments, total_length=4.0)
        subs = result["optimized_subs"]

        self.assertEqual(subs[0].content, "前一句表达了一个核心意思。")
        self.assertEqual(subs[1].content, "后一句把这个意思说得更准确。")
        self.assertEqual(subs[2].content, segments[2]["text"])

    @patch("autocut.auto_edit.llm_utils.chat_completion")
    def test_optimize_pass_large_rewrite_fallback_to_original(self, mock_chat):
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 前面这句表达了一个意思。",
                    "[L0002] 后面把同一个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点。",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 前面这句表达了一个意思并且我额外补充很多完全不相关的新内容导致长度大幅增加。",
                    "[L0002] 后一句把这个意思说得更准确。",
                    "[L0003] 最后补充一个新的信息点，确保逻辑完整。",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        segments = _sample_segments()
        result = editor._auto_edit_segments(segments, total_length=4.0)
        subs = result["optimized_subs"]

        self.assertEqual(subs[0].content, segments[0]["text"])
        self.assertEqual(subs[1].content, "后一句把这个意思说得更准确。")


if __name__ == "__main__":
    unittest.main()
