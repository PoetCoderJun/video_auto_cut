from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from web_api.utils import srt_utils
from web_api.utils.srt_utils import build_step1_lines_from_srt


class BuildStep1LinesFromSrtTest(unittest.TestCase):
    def test_legacy_dual_srt_builder_is_removed(self) -> None:
        self.assertFalse(hasattr(srt_utils, "build_step1_lines_from_srts"))

    def test_step1_lines_follow_optimized_srt_granularity(self) -> None:
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

            lines = build_step1_lines_from_srt(optimized_srt, "utf-8")

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
                        "<<REMOVE>> 前一句删掉",
                        "",
                        "2",
                        "00:00:01,100 --> 00:00:02,500",
                        "后一句保留",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            lines = build_step1_lines_from_srt(optimized_srt, "utf-8")

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["original_text"], "前一句删掉")
        self.assertEqual(lines[0]["optimized_text"], "前一句删掉")
        self.assertTrue(lines[0]["ai_suggest_remove"])
        self.assertTrue(lines[0]["user_final_remove"])
        self.assertEqual(lines[1]["optimized_text"], "后一句保留")
        self.assertFalse(lines[1]["user_final_remove"])


if __name__ == "__main__":
    unittest.main()
