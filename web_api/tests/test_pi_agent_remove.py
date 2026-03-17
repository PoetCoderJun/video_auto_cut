from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.editing.pi_agent_remove import PiAgentRemoveLoop, _json_loads


class PiAgentRemoveLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = PiAgentRemoveLoop(
            llm_config={
                "base_url": "https://example.com/v1",
                "model": "kimi-k2.5",
                "api_key": "test-key",
            }
        )
        self.segments = [
            {"id": 8, "start": 35.004, "end": 39.932, "text": "不用反复重复"},
            {"id": 11, "start": 40.412, "end": 47.052, "text": "不用反复重头录制"},
        ]

    def test_inspect_prompt_describes_retake_background(self) -> None:
        messages = self.loop.build_remove_inspect_prompt(self.segments)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("后面的行重新表达了前面已经说过的语义", messages[0]["content"])
        self.assertIn("只处理前文被后文覆盖的重复部分", messages[0]["content"])
        self.assertIn("[L0008]", messages[1]["content"])
        self.assertIn("[L0011]", messages[1]["content"])

    def test_json_loads_tolerates_trailing_commas_in_code_fence(self) -> None:
        payload = _json_loads(
            """
            ```json
            {
              "decisions": [
                {"line_id": 8, "action": "KEEP", "edited_text": "不用反复重复", "reason": "保留", "confidence": 0.91},
                {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "最终版本", "confidence": 0.95},
              ],
            }
            ```
            """
        )

        self.assertEqual(len(payload["decisions"]), 2)
        self.assertEqual(payload["decisions"][1]["line_id"], 11)

    @patch("video_auto_cut.editing.pi_agent_remove.llm_utils.chat_completion")
    def test_run_uses_single_pass_structured_decisions(self, mock_chat_completion) -> None:
        mock_chat_completion.return_value = """
        {
          "decisions": [
            {"line_id": 8, "action": "REMOVE", "edited_text": "", "reason": "被后一句覆盖", "confidence": 0.94},
            {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "最终版本", "confidence": 0.95}
          ]
        }
        """

        result = self.loop.run(self.segments)

        self.assertEqual([decision.remove_action for decision in result.decisions], ["REMOVE", "KEEP"])
        self.assertEqual(result.decisions[0].reason, "被后一句覆盖")
        self.assertGreaterEqual(result.decisions[0].confidence, 0.94)
        self.assertEqual(result.debug["iterations"], 1)
        self.assertIsNone(result.debug["critique"])
        self.assertEqual(mock_chat_completion.call_count, 1)

    @patch("video_auto_cut.editing.pi_agent_remove.llm_utils.chat_completion")
    def test_run_stops_after_draft(self, mock_chat_completion) -> None:
        mock_chat_completion.return_value = """
        {
          "decisions": [
            {"line_id": 8, "action": "REMOVE", "edited_text": "", "reason": "被后一句覆盖", "confidence": 0.93},
            {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "最终版本", "confidence": 0.96}
          ]
        }
        """

        result = self.loop.run(self.segments)

        self.assertEqual(mock_chat_completion.call_count, 1)
        self.assertEqual(result.decisions[0].remove_action, "REMOVE")
        self.assertEqual(result.debug["iterations"], 1)
        self.assertEqual(result.debug["final_source"], "draft")

    @patch("video_auto_cut.editing.pi_agent_remove.llm_utils.chat_completion")
    def test_run_falls_back_to_original_text_when_edited_text_missing(self, mock_chat_completion) -> None:
        mock_chat_completion.return_value = """
        {
          "decisions": [
            {"line_id": 8, "action": "KEEP", "edited_text": "", "reason": "未填写编辑文本", "confidence": 0.60},
            {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "最终版本", "confidence": 0.91}
          ]
        }
        """

        result = self.loop.run(self.segments)

        self.assertEqual(result.decisions[0].remove_action, "KEEP")
        self.assertEqual(result.decisions[0].current_text, "不用反复重复")
        self.assertEqual(result.debug["final_source"], "draft")

    @patch("video_auto_cut.editing.pi_agent_remove.llm_utils.chat_completion")
    def test_run_keeps_unique_prefix_and_only_removes_repeated_suffix(self, mock_chat_completion) -> None:
        segments = [
            {"id": 9, "start": 36.812, "end": 39.932, "text": "录口播时候你可以随便讲错，不用反复重复"},
            {"id": 11, "start": 40.412, "end": 47.052, "text": "不用反复重头录制"},
        ]
        mock_chat_completion.side_effect = [
            """
            {
              "decisions": [
                {"line_id": 9, "action": "KEEP", "edited_text": "录口播时候你可以随便讲错", "reason": "只删除被后文覆盖的重复尾部", "confidence": 0.95},
                {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "后文保留", "confidence": 0.96}
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

        result = self.loop.run(segments)

        self.assertEqual(result.decisions[0].remove_action, "KEEP")
        self.assertEqual(result.decisions[0].current_text, "录口播时候你可以随便讲错")
        self.assertEqual(result.decisions[1].current_text, "不用反复重头录制")

    @patch("video_auto_cut.editing.pi_agent_remove.llm_utils.chat_completion")
    def test_run_falls_back_to_keep_when_json_is_invalid(self, mock_chat_completion) -> None:
        mock_chat_completion.return_value = """
        {
          "decisions": [
            {"line_id": 8, "action": "REMOVE", "edited_text": "", "reason": "被后一句覆盖", "confidence": 0.94}
            {"line_id": 11, "action": "KEEP", "edited_text": "不用反复重头录制", "reason": "最终版本", "confidence": 0.95}
          ]
        }
        """

        result = self.loop.run(self.segments)

        self.assertEqual([decision.remove_action for decision in result.decisions], ["KEEP", "KEEP"])
        self.assertEqual(result.decisions[0].current_text, "不用反复重复")
        self.assertEqual(result.decisions[1].current_text, "不用反复重头录制")
        self.assertEqual(result.debug["final_source"], "parse_fallback")
        self.assertIn("Failed to parse LLM JSON payload", result.debug["error"])


if __name__ == "__main__":
    unittest.main()
