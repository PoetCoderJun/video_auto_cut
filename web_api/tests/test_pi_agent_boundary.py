from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.editing.pi_agent_boundary import (
    PiAgentBoundaryReview,
    _json_loads,
    apply_boundary_review,
)
from video_auto_cut.editing.pi_agent_models import (
    BoundaryReviewState,
    ChunkExecutionState,
    ChunkWindow,
    LineDecision,
    MergedGroup,
)


class PiAgentBoundaryReviewTest(unittest.TestCase):
    @staticmethod
    def _decision(line_id: int, text: str) -> LineDecision:
        return LineDecision(
            line_id=line_id,
            original_text=text,
            current_text=text,
            remove_action="KEEP",
            reason="keep",
            confidence=0.9,
        )

    def _chunk_state(
        self,
        chunk_id: int,
        core_start: int,
        core_end: int,
        left_overlap: int,
        right_overlap: int,
        line_ids: list[int],
    ) -> ChunkExecutionState:
        return ChunkExecutionState(
            window=ChunkWindow(
                chunk_id=chunk_id,
                context_start=core_start - left_overlap,
                context_end=core_end + right_overlap,
                core_start=core_start,
                core_end=core_end,
                left_overlap=left_overlap,
                right_overlap=right_overlap,
            ),
            decisions=[self._decision(line_id, f"line {line_id}") for line_id in line_ids],
            merged_groups=[
                MergedGroup(
                    source_line_ids=[line_id],
                    text=f"group {line_id}",
                    start=float(line_id),
                    end=float(line_id) + 0.8,
                )
                for line_id in line_ids
            ],
            core_line_ids=list(line_ids),
        )

    def setUp(self) -> None:
        self.reviewer = PiAgentBoundaryReview(
            llm_config={
                "base_url": "https://example.com/v1",
                "model": "kimi-k2.5",
                "api_key": "test-key",
            }
        )

    def test_prompt_uses_only_overlap_lines(self) -> None:
        previous_state = self._chunk_state(1, 1, 30, 0, 4, list(range(1, 35)))
        current_state = self._chunk_state(2, 31, 60, 4, 4, list(range(27, 65)))

        messages = self.reviewer.build_boundary_review_prompt(previous_state, current_state)

        self.assertIn("[L0027]", messages[1]["content"])
        self.assertIn("[L0034]", messages[1]["content"])
        self.assertNotIn("[L0005]", messages[1]["content"])
        self.assertNotIn("[L0058]", messages[1]["content"])

    def test_json_loads_tolerates_trailing_commas_in_code_fence(self) -> None:
        payload = _json_loads(
            """
            ```json
            {
              "dropped_line_ids": [30,],
              "reason": "后一个 chunk 的开头是最终版本",
            }
            ```
            """
        )

        self.assertEqual(payload["dropped_line_ids"], [30])

    @patch("video_auto_cut.editing.pi_agent_boundary.llm_utils.chat_completion")
    def test_run_returns_boundary_review_state(self, mock_chat_completion) -> None:
        previous_state = self._chunk_state(1, 1, 30, 0, 4, list(range(1, 35)))
        current_state = self._chunk_state(2, 31, 60, 4, 4, list(range(27, 65)))
        mock_chat_completion.return_value = """
        {
          "dropped_line_ids": [30],
          "reason": "后一个 chunk 的开头是最终版本"
        }
        """

        review = self.reviewer.run(previous_state, current_state)

        self.assertEqual(review.previous_chunk_id, 1)
        self.assertEqual(review.current_chunk_id, 2)
        self.assertEqual(review.dropped_line_ids, [30])

    @patch("video_auto_cut.editing.pi_agent_boundary.llm_utils.chat_completion")
    def test_run_falls_back_to_no_drops_when_json_is_invalid(self, mock_chat_completion) -> None:
        previous_state = self._chunk_state(1, 1, 30, 0, 4, list(range(1, 35)))
        current_state = self._chunk_state(2, 31, 60, 4, 4, list(range(27, 65)))
        mock_chat_completion.return_value = """
        {
          "dropped_line_ids": [30]
          "reason": "后一个 chunk 的开头是最终版本"
        }
        """

        review = self.reviewer.run(previous_state, current_state)

        self.assertEqual(review.previous_chunk_id, 1)
        self.assertEqual(review.current_chunk_id, 2)
        self.assertEqual(review.dropped_line_ids, [])
        self.assertEqual(review.reason, "解析失败回退")

    def test_apply_boundary_review_drops_previous_decision_and_preserves_provenance(self) -> None:
        previous_state = self._chunk_state(1, 1, 30, 0, 4, [29, 30])
        current_state = self._chunk_state(2, 31, 60, 4, 0, [31, 32])
        review = BoundaryReviewState(
            previous_chunk_id=1,
            current_chunk_id=2,
            dropped_line_ids=[30],
            reason="后一个 chunk 的开头是最终版本",
        )

        next_previous, next_current = apply_boundary_review(previous_state, current_state, review)

        self.assertEqual([decision.line_id for decision in next_previous.decisions], [29])
        self.assertEqual([group.source_line_ids for group in next_previous.merged_groups], [[29]])
        self.assertEqual([group.source_line_ids for group in next_current.merged_groups], [[31], [32]])
        self.assertEqual(next_previous.core_line_ids, [29, 30])
        self.assertEqual(next_current.core_line_ids, [31, 32])


if __name__ == "__main__":
    unittest.main()
