from __future__ import annotations

import unittest

from video_auto_cut.asr.dashscope_filetrans import (
    DashScopeFiletransClient,
    DashScopeFiletransConfig,
)
from video_auto_cut.asr.filetrans_like import FiletransSegment
from video_auto_cut.asr.transcribe import Transcribe


def _client() -> DashScopeFiletransClient:
    return DashScopeFiletransClient(
        DashScopeFiletransConfig(
            base_url="https://example.com",
            api_key="test-key",
            model="test-model",
            task=None,
            poll_seconds=1.0,
            timeout_seconds=30.0,
            language_hints=(),
            context="",
            enable_words=True,
            word_split_enabled=True,
            word_split_on_comma=True,
            word_split_comma_pause_s=0.4,
            word_split_min_chars=12,
            word_vad_gap_s=1.0,
            word_max_segment_s=8.0,
        )
    )


class AsrSplitGranularityTest(unittest.TestCase):
    def test_word_split_breaks_on_single_comma(self) -> None:
        words = [
            {"begin_time": 0, "end_time": 400, "text": "打开", "punctuation": ""},
            {"begin_time": 400, "end_time": 800, "text": "网站", "punctuation": "，"},
            {"begin_time": 850, "end_time": 1200, "text": "上传", "punctuation": ""},
            {"begin_time": 1200, "end_time": 1600, "text": "视频", "punctuation": "。"},
        ]
        segments = _client()._split_by_words(words)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "打开网站，")
        self.assertEqual(segments[1].text, "上传视频。")

    def test_punctuation_split_breaks_on_single_comma(self) -> None:
        source = [FiletransSegment(start=0.0, end=2.0, text="打开网站，上传视频。")]
        pieces = Transcribe._split_segments_by_punctuation(source)
        self.assertEqual(len(pieces), 2)
        self.assertEqual(pieces[0].text, "打开网站，")
        self.assertEqual(pieces[1].text, "上传视频。")


if __name__ == "__main__":
    unittest.main()
