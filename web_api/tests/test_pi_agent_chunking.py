from __future__ import annotations

import unittest

from video_auto_cut.editing.auto_edit import (
    AUTO_EDIT_CHUNK_LINES,
    AUTO_EDIT_CHUNK_OVERLAP_LINES,
)
from video_auto_cut.editing.pi_agent_chunking import build_chunk_windows


class PiAgentChunkingTest(unittest.TestCase):
    @staticmethod
    def _make_segments(count: int) -> list[dict[str, object]]:
        return [
            {
                "id": index,
                "start": float(index - 1),
                "end": float(index),
                "text": f"line {index}",
            }
            for index in range(1, count + 1)
        ]

    def test_single_chunk_uses_entire_range_with_right_overlap_only(self) -> None:
        windows = build_chunk_windows(self._make_segments(18))

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].chunk_id, 1)
        self.assertEqual(windows[0].context_start, 1)
        self.assertEqual(windows[0].context_end, 18)
        self.assertEqual(windows[0].core_start, 1)
        self.assertEqual(windows[0].core_end, 18)
        self.assertEqual(windows[0].left_overlap, 0)
        self.assertEqual(windows[0].right_overlap, 0)

    def test_exact_chunk_size_does_not_create_extra_chunk(self) -> None:
        windows = build_chunk_windows(self._make_segments(AUTO_EDIT_CHUNK_LINES))

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].core_end - windows[0].core_start + 1, AUTO_EDIT_CHUNK_LINES)

    def test_second_chunk_includes_left_and_right_overlap(self) -> None:
        windows = build_chunk_windows(self._make_segments(65))

        self.assertEqual(len(windows), 3)
        second = windows[1]
        self.assertEqual(second.chunk_id, 2)
        self.assertEqual(second.core_start, 31)
        self.assertEqual(second.core_end, 60)
        self.assertEqual(second.left_overlap, AUTO_EDIT_CHUNK_OVERLAP_LINES)
        self.assertEqual(second.right_overlap, AUTO_EDIT_CHUNK_OVERLAP_LINES)
        self.assertEqual(second.context_start, 27)
        self.assertEqual(second.context_end, 64)

    def test_last_chunk_truncates_right_overlap_at_end(self) -> None:
        windows = build_chunk_windows(self._make_segments(65))

        last = windows[-1]
        self.assertEqual(last.chunk_id, 3)
        self.assertEqual(last.core_start, 61)
        self.assertEqual(last.core_end, 65)
        self.assertEqual(last.left_overlap, AUTO_EDIT_CHUNK_OVERLAP_LINES)
        self.assertEqual(last.right_overlap, 0)
        self.assertEqual(last.context_start, 57)
        self.assertEqual(last.context_end, 65)


if __name__ == "__main__":
    unittest.main()
