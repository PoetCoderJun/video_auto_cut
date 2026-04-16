from __future__ import annotations

import unittest

from video_auto_cut.editing.chapter_domain import canonicalize_test_chapters, ensure_full_block_coverage


class ChapterInvariantsSharedTests(unittest.TestCase):
    def test_canonicalize_recomputes_timings_and_block_ranges(self) -> None:
        kept_lines = [
            {"line_id": 1, "start": 0.0, "end": 1.0, "user_final_remove": False},
            {"line_id": 2, "start": 1.0, "end": 2.0, "user_final_remove": False},
            {"line_id": 3, "start": 2.0, "end": 4.0, "user_final_remove": False},
        ]
        chapters = canonicalize_test_chapters(
            [
                {"chapter_id": 1, "title": "开场", "block_range": "1-2"},
                {"chapter_id": 2, "title": "结尾", "block_range": "3"},
            ],
            kept_lines,
        )
        self.assertEqual(chapters[0]["start"], 0.0)
        self.assertEqual(chapters[0]["end"], 2.0)
        self.assertEqual(chapters[1]["block_range"], "3")

    def test_full_block_coverage_rejects_gaps(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not contiguous"):
            ensure_full_block_coverage(
                [
                    {"chapter_id": 1, "title": "开场", "block_range": "1"},
                    {"chapter_id": 2, "title": "结尾", "block_range": "3"},
                ],
                total_blocks=3,
            )


if __name__ == "__main__":
    unittest.main()
