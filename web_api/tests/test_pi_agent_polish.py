from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.editing.pi_agent_models import LineDecision
from video_auto_cut.editing.pi_agent_polish import PiAgentPolishLoop


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


if __name__ == "__main__":
    unittest.main()
