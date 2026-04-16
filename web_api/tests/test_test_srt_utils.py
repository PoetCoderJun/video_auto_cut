from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_auto_cut.shared import test_text_io as srt_utils
from video_auto_cut.shared.test_text_io import (
    build_test_chapters_from_text,
    build_test_lines_from_json,
    build_test_lines_from_srt,
    build_test_lines_from_text,
    write_chapters_text,
    write_final_test_srt,
    write_test_json,
    write_test_text,
)


class BuildTestLinesFromSrtTest(unittest.TestCase):
    def test_legacy_dual_srt_builder_is_removed(self) -> None:
        self.assertFalse(hasattr(srt_utils, "build_test_lines_from_srts"))

    def test_test_lines_follow_optimized_srt_granularity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            optimized_srt = Path(tmpdir) / "optimized.srt"

            optimized_srt.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:01,000",
                        "上次我发了自己写的AI剪口播工具的视频，",
                        "",
                        "2",
                        "00:00:01,100 --> 00:00:03,000",
                        "有几百个人想试用，，但那时候它还只是个技术项目，",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            lines = build_test_lines_from_srt(optimized_srt, "utf-8")

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["line_id"], 1)
        self.assertEqual(lines[1]["line_id"], 2)
        self.assertEqual(lines[0]["optimized_text"], "上次我发了自己写的AI剪口播工具的视频，")
        self.assertEqual(lines[1]["optimized_text"], "有几百个人想试用，，但那时候它还只是个技术项目，")
        self.assertFalse(lines[1]["user_final_remove"])
        self.assertFalse(lines[1]["ai_suggest_remove"])

    def test_remove_lines_are_kept_as_recoverable_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            optimized_srt = Path(tmpdir) / "optimized.srt"
            optimized_srt.write_text(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:01,000",
                        "<remove>前一句删掉",
                        "",
                        "2",
                        "00:00:01,100 --> 00:00:02,500",
                        "后一句保留",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            lines = build_test_lines_from_srt(optimized_srt, "utf-8")

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["original_text"], "前一句删掉")
        self.assertEqual(lines[0]["optimized_text"], "前一句删掉")
        self.assertTrue(lines[0]["ai_suggest_remove"])
        self.assertTrue(lines[0]["user_final_remove"])
        self.assertEqual(lines[1]["optimized_text"], "后一句保留")
        self.assertFalse(lines[1]["user_final_remove"])

    def test_build_test_lines_from_json_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "optimized.test.json"
            sidecar.write_text(
                """
                {
                  "lines": [
                    {
                      "line_id": 2,
                      "start": 1.1,
                      "end": 2.5,
                      "original_text": "后一句保留",
                      "optimized_text": "后一句保留",
                      "ai_suggest_remove": false,
                      "user_final_remove": false
                    },
                    {
                      "line_id": 1,
                      "start": 0.0,
                      "end": 1.0,
                      "original_text": "前一句删掉",
                      "optimized_text": "前一句删掉",
                      "ai_suggest_remove": true,
                      "user_final_remove": true
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            lines = build_test_lines_from_json(sidecar)

        self.assertEqual([line["line_id"] for line in lines], [1, 2])
        self.assertTrue(lines[0]["ai_suggest_remove"])
        self.assertEqual(lines[1]["optimized_text"], "后一句保留")

    def test_build_test_lines_from_text_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar = Path(tmpdir) / "optimized.test.txt"
            sidecar.write_text(
                "【00:00:00.000-00:00:01.000】<remove>前一句删掉\n"
                "【00:00:01.100-00:00:02.500】后一句保留\n",
                encoding="utf-8",
            )

            lines = build_test_lines_from_text(sidecar)

        self.assertEqual([line["line_id"] for line in lines], [1, 2])
        self.assertTrue(lines[0]["ai_suggest_remove"])
        self.assertEqual(lines[1]["optimized_text"], "后一句保留")

    def test_write_test_json_round_trip_preserves_sorted_line_semantics(self) -> None:
        lines = [
            {
                "line_id": 2,
                "start": 1.1,
                "end": 2.5,
                "original_text": "后一句保留",
                "optimized_text": "后一句保留-润色",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "前一句删掉",
                "optimized_text": "前一句删掉",
                "ai_suggest_remove": True,
                "user_final_remove": True,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "draft.test.json"
            write_test_json(lines, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            round_tripped = build_test_lines_from_json(path)

        self.assertEqual(len(payload["lines"]), 2)
        self.assertEqual([line["line_id"] for line in round_tripped], [1, 2])
        self.assertTrue(round_tripped[0]["user_final_remove"])
        self.assertEqual(round_tripped[1]["optimized_text"], "后一句保留-润色")

    def test_write_test_text_round_trip_preserves_remove_flag_and_text(self) -> None:
        lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "前一句删掉",
                "optimized_text": "前一句删掉",
                "ai_suggest_remove": True,
                "user_final_remove": True,
            },
            {
                "line_id": 2,
                "start": 1.1,
                "end": 2.5,
                "original_text": "后一句保留",
                "optimized_text": "后一句保留-润色",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "draft.test.txt"
            write_test_text(lines, path)
            round_tripped = build_test_lines_from_text(path)

        self.assertEqual([line["line_id"] for line in round_tripped], [1, 2])
        self.assertTrue(round_tripped[0]["user_final_remove"])
        self.assertEqual(round_tripped[0]["original_text"], "前一句删掉")
        self.assertEqual(round_tripped[1]["optimized_text"], "后一句保留-润色")

    def test_write_final_test_srt_round_trip_keeps_remove_token_at_boundary_only(self) -> None:
        lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "前一句删掉",
                "optimized_text": "不应泄漏这个字段",
                "ai_suggest_remove": True,
                "user_final_remove": True,
            },
            {
                "line_id": 2,
                "start": 1.1,
                "end": 2.5,
                "original_text": "后一句保留",
                "optimized_text": "后一句保留-润色",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "final_test.srt"
            write_final_test_srt(lines, path, "utf-8")
            raw_srt = path.read_text(encoding="utf-8")
            round_tripped = build_test_lines_from_srt(path, "utf-8")

        self.assertIn("<remove>前一句删掉", raw_srt)
        self.assertNotIn("<remove>后一句保留-润色", raw_srt)
        self.assertEqual(round_tripped[0]["original_text"], "前一句删掉")
        self.assertEqual(round_tripped[0]["optimized_text"], "前一句删掉")
        self.assertNotIn("<remove>", round_tripped[0]["original_text"])
        self.assertNotIn("<remove>", round_tripped[0]["optimized_text"])
        self.assertEqual(round_tripped[1]["optimized_text"], "后一句保留-润色")

    def test_chapter_text_round_trip_uses_canonicalized_timings(self) -> None:
        kept_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "第一句",
                "optimized_text": "第一句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 2,
                "start": 1.0,
                "end": 2.5,
                "original_text": "第二句",
                "optimized_text": "第二句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]
        chapters = [{"chapter_id": 9, "title": "确认稿", "start": 999.0, "end": 1000.0, "block_range": "1-2"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "chapters.txt"
            write_chapters_text(chapters, path)
            round_tripped = build_test_chapters_from_text(path, kept_lines=kept_lines)

        self.assertEqual(
            round_tripped,
            [{"chapter_id": 1, "title": "确认稿", "start": 0.0, "end": 2.5, "block_range": "1-2"}],
        )


if __name__ == "__main__":
    unittest.main()
