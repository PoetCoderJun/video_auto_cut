from __future__ import annotations

import unittest

from video_auto_cut.editing.pi_agent_merge import build_merged_groups
from video_auto_cut.editing.pi_agent_models import LineDecision


class PiAgentMergeTest(unittest.TestCase):
    @staticmethod
    def _make_segments(texts: list[str]) -> list[dict[str, object]]:
        segments: list[dict[str, object]] = []
        start = 0.0
        for index, text in enumerate(texts, start=1):
            segments.append(
                {
                    "id": index,
                    "start": start,
                    "end": start + 1.0,
                    "text": text,
                }
            )
            start += 1.2
        return segments

    @staticmethod
    def _make_decision(
        line_id: int, text: str, action: str = "KEEP"
    ) -> LineDecision:
        return LineDecision(
            line_id=line_id,
            original_text=text,
            current_text=text,
            remove_action=action,
            reason="test",
            confidence=0.9,
        )

    def test_only_keep_lines_participate_in_merge(self) -> None:
        segments = self._make_segments(["短句一", "这句删除", "这句很长足够超过二十个字不需要继续合并"])
        decisions = [
            self._make_decision(1, "短句一"),
            self._make_decision(2, "这句删除", action="REMOVE"),
            self._make_decision(3, "这句很长足够超过二十个字不需要继续合并"),
        ]

        groups = build_merged_groups(segments, decisions, threshold=20)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].source_line_ids, [1])
        self.assertEqual(groups[1].source_line_ids, [3])

    def test_remove_lines_hard_stop_merge_chain(self) -> None:
        segments = self._make_segments(["短句一", "这句删除", "短句二", "这句很长足够超过二十个字不需要继续合并"])
        decisions = [
            self._make_decision(1, "短句一"),
            self._make_decision(2, "这句删除", action="REMOVE"),
            self._make_decision(3, "短句二"),
            self._make_decision(4, "这句很长足够超过二十个字不需要继续合并"),
        ]

        groups = build_merged_groups(segments, decisions, threshold=20)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].text, "短句一")
        self.assertEqual(groups[1].text, "短句二，这句很长足够超过二十个字不需要继续合并")
        self.assertEqual(groups[1].source_line_ids, [3, 4])

    def test_merge_records_source_line_ids_and_timing(self) -> None:
        segments = self._make_segments(["短句一", "这句很长足够超过二十个字不需要继续合并"])
        decisions = [
            self._make_decision(1, "短句一"),
            self._make_decision(2, "这句很长足够超过二十个字不需要继续合并"),
        ]

        groups = build_merged_groups(segments, decisions, threshold=20)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].source_line_ids, [1, 2])
        self.assertEqual(groups[0].start, 0.0)
        self.assertEqual(groups[0].end, 2.2)

    def test_question_mark_preserves_boundary_without_comma(self) -> None:
        segments = self._make_segments(["你知道为什么吗？", "因为这里要保留问句"])
        decisions = [
            self._make_decision(1, "你知道为什么吗？"),
            self._make_decision(2, "因为这里要保留问句"),
        ]

        groups = build_merged_groups(segments, decisions, threshold=20)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].text, "你知道为什么吗？因为这里要保留问句")


if __name__ == "__main__":
    unittest.main()
