from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import srt

from video_auto_cut.rendering.cut import build_merged_segments, filter_kept_subtitles
from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt


class CutFromOptimizedSrtContractTests(unittest.TestCase):
    def test_filter_kept_subtitles_only_depends_on_boundary_srt_markers(self) -> None:
        subs = list(
            srt.parse(
                "\n".join(
                    [
                        "1",
                        "00:00:00,000 --> 00:00:01,000",
                        "<remove>前一句删掉",
                        "",
                        "2",
                        "00:00:01,000 --> 00:00:02,200",
                        "后一句保留",
                        "",
                        "3",
                        "00:00:02,200 --> 00:00:03,000",
                        "旧决策头也要被过滤",
                        "",
                    ]
                )
            )
        )

        kept = filter_kept_subtitles(subs)

        self.assertEqual(len(kept), 2)
        self.assertEqual([sub.index for sub in kept], [2, 3])
        self.assertEqual([sub.content for sub in kept], ["后一句保留", "旧决策头也要被过滤"])

    def test_build_merged_segments_merges_only_kept_subtitles(self) -> None:
        kept = list(
            srt.parse(
                "\n".join(
                    [
                        "2",
                        "00:00:01,000 --> 00:00:02,000",
                        "后一句保留",
                        "",
                        "4",
                        "00:00:02,100 --> 00:00:03,100",
                        "再补一句",
                        "",
                    ]
                )
            )
        )

        segments = build_merged_segments(kept, merge_gap_s=0.2)

        self.assertEqual(segments, [{"start": 1.0, "end": 3.1}])

    def test_build_cut_srt_from_optimized_srt_preserves_boundary_contract_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.optimized.srt"
            out = Path(tmpdir) / "cut.srt"
            src.write_text(
                "\n".join(
                    [
                        "7",
                        "00:00:00,000 --> 00:00:01,000",
                        "<remove>前一句删掉",
                        "",
                        "11",
                        "00:00:01,000 --> 00:00:02,000",
                        "后一句保留",
                        "",
                        "12",
                        "00:00:02,050 --> 00:00:03,050",
                        "再补一句",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = build_cut_srt_from_optimized_srt(
                source_srt_path=str(src),
                output_srt_path=str(out),
                encoding="utf-8",
                merge_gap_s=0.1,
                preserve_input_indices=True,
            )

            written = list(srt.parse(out.read_text(encoding="utf-8")))

        self.assertEqual([sub.index for sub in written], [11, 12])
        self.assertEqual([sub.content for sub in written], ["后一句保留", "再补一句"])
        self.assertEqual(result["segments"], [{"start": 1.0, "end": 3.05}])
        self.assertEqual(
            result["captions"],
            [
                {"index": 11, "start": 0.0, "end": 1.0, "text": "后一句保留"},
                {"index": 12, "start": 1.05, "end": 2.05, "text": "再补一句"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
