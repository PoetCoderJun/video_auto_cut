from __future__ import annotations

import unittest

from video_auto_cut.editing.pi_agent_models import (
    BoundaryReviewState,
    ChunkExecutionState,
    ChunkWindow,
    LineDecision,
    MergedGroup,
)


class PiAgentModelsTest(unittest.TestCase):
    def test_chunk_window_serializes_core_and_context_ranges(self) -> None:
        window = ChunkWindow(
            chunk_id=2,
            context_start=27,
            context_end=64,
            core_start=31,
            core_end=60,
            left_overlap=4,
            right_overlap=4,
        )

        self.assertEqual(
            window.to_dict(),
            {
                "chunk_id": 2,
                "context_start": 27,
                "context_end": 64,
                "core_start": 31,
                "core_end": 60,
                "left_overlap": 4,
                "right_overlap": 4,
            },
        )

    def test_line_decision_tracks_action_reason_and_confidence(self) -> None:
        decision = LineDecision(
            line_id=11,
            original_text="不用反复重头录制",
            current_text="不用反复重头录制",
            remove_action="KEEP",
            reason="后一句是最终表达",
            confidence=0.91,
        )

        self.assertEqual(decision.line_id, 11)
        self.assertEqual(decision.remove_action, "KEEP")
        self.assertEqual(decision.reason, "后一句是最终表达")
        self.assertAlmostEqual(decision.confidence, 0.91)
        self.assertEqual(
            decision.to_dict(),
            {
                "line_id": 11,
                "original_text": "不用反复重头录制",
                "current_text": "不用反复重头录制",
                "remove_action": "KEEP",
                "reason": "后一句是最终表达",
                "confidence": 0.91,
                "source_line_ids": [11],
            },
        )

    def test_merged_group_keeps_source_line_ids_and_timing(self) -> None:
        merged = MergedGroup(
            source_line_ids=[8, 11],
            text="录口播时候你可以随便讲错，不用反复重头录制",
            start=35.004,
            end=47.052,
        )

        self.assertEqual(merged.source_line_ids, [8, 11])
        self.assertEqual(
            merged.to_dict(),
            {
                "source_line_ids": [8, 11],
                "text": "录口播时候你可以随便讲错，不用反复重头录制",
                "start": 35.004,
                "end": 47.052,
            },
        )

    def test_chunk_execution_state_exposes_decisions_and_merged_groups(self) -> None:
        state = ChunkExecutionState(
            window=ChunkWindow(
                chunk_id=1,
                context_start=1,
                context_end=30,
                core_start=1,
                core_end=30,
                left_overlap=0,
                right_overlap=4,
            ),
            decisions=[
                LineDecision(
                    line_id=8,
                    original_text="不用反复重复",
                    current_text="不用反复重复",
                    remove_action="REMOVE",
                    reason="被后一句覆盖",
                    confidence=0.87,
                )
            ],
            merged_groups=[
                MergedGroup(
                    source_line_ids=[11],
                    text="不用反复重头录制",
                    start=40.412,
                    end=47.052,
                )
            ],
        )

        payload = state.to_dict()

        self.assertEqual(payload["window"]["chunk_id"], 1)
        self.assertEqual(payload["decisions"][0]["remove_action"], "REMOVE")
        self.assertEqual(payload["merged_groups"][0]["source_line_ids"], [11])

    def test_boundary_review_state_tracks_overlap_fixups(self) -> None:
        review = BoundaryReviewState(
            previous_chunk_id=1,
            current_chunk_id=2,
            dropped_line_ids=[30],
            reason="后一个 chunk 的开头句是最终版本",
        )

        self.assertEqual(
            review.to_dict(),
            {
                "previous_chunk_id": 1,
                "current_chunk_id": 2,
                "dropped_line_ids": [30],
                "reason": "后一个 chunk 的开头句是最终版本",
            },
        )


if __name__ == "__main__":
    unittest.main()
