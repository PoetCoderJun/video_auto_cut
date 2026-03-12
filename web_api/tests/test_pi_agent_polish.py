from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.editing.pi_agent_models import LineDecision, MergedGroup
from video_auto_cut.editing.pi_agent_polish import (
    PiAgentChunkPolishLoop,
    PiAgentPolishLoop,
    _json_loads,
)


class PiAgentPolishLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = PiAgentPolishLoop(
            llm_config={
                "base_url": "https://example.com/v1",
                "model": "kimi-k2.5",
                "api_key": "test-key",
            }
        )
        self.decisions = [
            LineDecision(
                line_id=8,
                original_text="录口播时候你可以随便讲错，",
                current_text="录口播时候你可以随便讲错，",
                remove_action="KEEP",
                reason="保留",
                confidence=0.9,
            ),
            LineDecision(
                line_id=10,
                original_text="不用重反复重复，",
                current_text="不用重反复重复，",
                remove_action="REMOVE",
                reason="被后句覆盖",
                confidence=0.95,
            ),
            LineDecision(
                line_id=11,
                original_text="啊，不用反复的重头录制。",
                current_text="啊，不用反复的重头录制。",
                remove_action="KEEP",
                reason="最终版本",
                confidence=0.95,
            ),
        ]

    def test_draft_prompt_mentions_line_ids(self) -> None:
        messages = self.loop.build_polish_draft_prompt(
            [decision for decision in self.decisions if decision.remove_action == "KEEP"]
        )

        self.assertIn("line_id", messages[1]["content"])
        self.assertIn("L0008", messages[1]["content"])
        self.assertIn("L0011", messages[1]["content"])
        self.assertNotIn("L0010", messages[1]["content"])

    def test_json_loads_tolerates_trailing_commas_in_code_fence(self) -> None:
        payload = _json_loads(
            """
            ```json
            {
              "lines": [
                {"line_id": 8, "text": "录口播的时候你可以随便讲错", "reason": "修正错字", "confidence": 0.93},
                {"line_id": 11, "text": "不用反复地重头录制", "reason": "去掉口头语", "confidence": 0.95},
              ],
            }
            ```
            """
        )

        self.assertEqual(len(payload["lines"]), 2)
        self.assertEqual(payload["lines"][1]["line_id"], 11)

    @patch("video_auto_cut.editing.pi_agent_polish.llm_utils.chat_completion")
    def test_run_polishes_keep_lines_and_preserves_remove_lines(self, mock_chat_completion) -> None:
        mock_chat_completion.side_effect = [
            """
            {
              "lines": [
                {"line_id": 8, "text": "录口播的时候你可以随便讲错", "reason": "修正错字", "confidence": 0.93},
                {"line_id": 11, "text": "不用反复地重头录制。", "reason": "去掉口头语", "confidence": 0.95}
              ]
            }
            """,
            """
            {
              "needs_revision": false,
              "issues": []
            }
            """,
        ]

        result = self.loop.run(self.decisions)

        self.assertEqual(mock_chat_completion.call_count, 2)
        self.assertEqual(result.decisions[0].current_text, "录口播的时候你可以随便讲错")
        self.assertEqual(result.decisions[1].current_text, "不用重反复重复，")
        self.assertEqual(result.decisions[1].remove_action, "REMOVE")
        self.assertEqual(result.decisions[2].current_text, "不用反复地重头录制")
        self.assertEqual(result.debug["final_source"], "draft")

    @patch("video_auto_cut.editing.pi_agent_polish.llm_utils.chat_completion")
    def test_run_uses_critique_to_fix_remaining_issue(self, mock_chat_completion) -> None:
        mock_chat_completion.side_effect = [
            """
            {
              "lines": [
                {"line_id": 8, "text": "录口播时候你可以随便讲错", "reason": "保留", "confidence": 0.81},
                {"line_id": 11, "text": "啊，不用反复的重头录制", "reason": "沿用原文", "confidence": 0.81}
              ]
            }
            """,
            """
            {
              "needs_revision": true,
              "issues": [
                {"line_id": 11, "message": "还保留了口头语 啊"}
              ]
            }
            """,
            """
            {
              "lines": [
                {"line_id": 8, "text": "录口播时候你可以随便讲错", "reason": "保留", "confidence": 0.92},
                {"line_id": 11, "text": "不用反复地重头录制", "reason": "移除口头语", "confidence": 0.95}
              ]
            }
            """,
        ]

        result = self.loop.run(self.decisions)

        self.assertEqual(result.decisions[2].current_text, "不用反复地重头录制")
        self.assertTrue(result.debug["critique"]["needs_revision"])
        self.assertEqual(result.debug["final_source"], "revise")

    @patch("video_auto_cut.editing.pi_agent_polish.llm_utils.chat_completion")
    def test_question_line_keeps_question_mark(self, mock_chat_completion) -> None:
        decisions = [
            LineDecision(
                line_id=21,
                original_text="你知道为什么吗？",
                current_text="你知道为什么吗？",
                remove_action="KEEP",
                reason="保留",
                confidence=0.9,
            )
        ]
        mock_chat_completion.side_effect = [
            """
            {
              "lines": [
                {"line_id": 21, "text": "你知道为什么吗？", "reason": "问句保留", "confidence": 0.97}
              ]
            }
            """,
            """
            {
              "needs_revision": false,
              "issues": []
            }
            """,
        ]

        result = self.loop.run(decisions)

        self.assertEqual(result.decisions[0].current_text, "你知道为什么吗？")


class PiAgentChunkPolishLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = PiAgentChunkPolishLoop(
            llm_config={
                "base_url": "https://example.com/v1",
                "model": "kimi-k2.5",
                "api_key": "test-key",
            }
        )
        self.groups = [
            MergedGroup(
                source_line_ids=[2, 3, 4],
                text="这里是俊，前段时间我发了续签香港签证的分享，还接受了凤凰卫视的采访",
                start=2.0,
                end=10.0,
            ),
            MergedGroup(
                source_line_ids=[6, 7, 8],
                text="2025年香港续签签证有四大变化，一分钟给大家总结，非常重要",
                start=11.0,
                end=16.0,
            ),
        ]

    def test_draft_prompt_mentions_chunk_ids_and_context(self) -> None:
        messages = self.loop.build_polish_draft_prompt(self.groups)

        self.assertIn("chunk_id", messages[1]["content"])
        self.assertIn("C0002", messages[1]["content"])
        self.assertIn("source_line_ids", messages[1]["content"])
        self.assertIn("大胆重写", messages[0]["content"])
        self.assertIn("可直接发布", messages[0]["content"])
        self.assertIn("不要拘泥于原句", messages[0]["content"])
        self.assertIn("优先修复明显的ASR错误", messages[0]["content"])
        self.assertIn("补全高概率缺失", messages[0]["content"])

    @patch("video_auto_cut.editing.pi_agent_polish.llm_utils.chat_completion")
    def test_run_rewrites_merged_groups(self, mock_chat_completion) -> None:
        mock_chat_completion.side_effect = [
            """
            {
              "chunks": [
                {"chunk_id": 2, "text": "前段时间我分享了香港续签签证经验，还接受了凤凰卫视采访，收到了很多相关私信", "reason": "修正口语与错词", "confidence": 0.95},
                {"chunk_id": 6, "text": "2025年香港续签有四大变化，我用一分钟给大家讲清楚", "reason": "压缩重写", "confidence": 0.93}
              ]
            }
            """,
            """
            {
              "needs_revision": false,
              "issues": []
            }
            """,
        ]

        result = self.loop.run(self.groups)

        self.assertEqual(mock_chat_completion.call_count, 2)
        self.assertEqual(
            result.groups[0].text,
            "前段时间我分享了香港续签签证经验，还接受了凤凰卫视采访，收到了很多相关私信",
        )
        self.assertEqual(
            result.groups[1].text,
            "2025年香港续签有四大变化，我用一分钟给大家讲清楚",
        )
        self.assertEqual(result.debug["final_source"], "draft")


if __name__ == "__main__":
    unittest.main()
