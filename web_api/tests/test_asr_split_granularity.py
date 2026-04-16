from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.asr.dashscope_filetrans import (
    _candidate_rows,
    _extract_transcription_url,
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
            language="zh",
            language_hints=(),
            text="香港续签",
            enable_itn=True,
            enable_words=True,
            channel_ids=(0,),
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

    def test_open_json_url_rejects_non_http_scheme(self) -> None:
        client = _client()
        with patch("video_auto_cut.asr.dashscope_filetrans.urllib.request.urlopen") as mock_urlopen:
            with self.assertRaises(RuntimeError) as ctx:
                client._open_json_url("file:///etc/passwd", headers={})
        self.assertIn("invalid", str(ctx.exception).lower())
        mock_urlopen.assert_not_called()

    def test_submit_payload_uses_documented_dashscope_fields(self) -> None:
        payload = _client()._build_submit_payload(
            file_url="https://example.com/audio.wav",
            language="zh",
            legacy_language_hints=["zh", "en"],
            text="香港签证续签",
            use_file_urls=False,
        )
        self.assertEqual(payload["input"]["file_url"], "https://example.com/audio.wav")
        self.assertEqual(payload["parameters"]["language"], "zh")
        self.assertEqual(payload["parameters"]["text"], "香港签证续签")
        self.assertTrue(payload["parameters"]["enable_itn"])
        self.assertTrue(payload["parameters"]["enable_words"])
        self.assertEqual(payload["parameters"]["channel_id"], [0])
        self.assertNotIn("context", payload["parameters"])
        self.assertNotIn("language_hints", payload["parameters"])

    def test_extract_transcription_url_supports_multiple_dashscope_shapes(self) -> None:
        self.assertEqual(
            _extract_transcription_url({"transcription_url": " https://example.com/direct.json "}),
            "https://example.com/direct.json",
        )
        self.assertEqual(
            _extract_transcription_url({"result": {"transcription_url": "https://example.com/nested.json"}}),
            "https://example.com/nested.json",
        )
        self.assertEqual(
            _extract_transcription_url(
                {
                    "results": [
                        {"ignored": "x"},
                        {"transcription_url": "https://example.com/from-results.json"},
                    ]
                }
            ),
            "https://example.com/from-results.json",
        )
        self.assertIsNone(_extract_transcription_url({}))

    def test_candidate_rows_collects_sentences_transcripts_and_segments(self) -> None:
        rows = _candidate_rows(
            {
                "sentences": [{"text": "顶层句子"}, "ignored"],
                "transcripts": [
                    {"sentences": [{"text": "转写句子"}]},
                    {"text": "转写回退"},
                    "ignored",
                ],
                "segments": [{"text": "原始片段"}],
            }
        )

        self.assertEqual(
            rows,
            [
                {"text": "顶层句子"},
                {"text": "转写句子"},
                {"text": "转写回退"},
                {"text": "原始片段"},
            ],
        )

    def test_cleanup_segments_drops_tiny_overlap_and_keeps_timeline_monotonic(self) -> None:
        cleaned = _client()._cleanup_segments(
            [
                FiletransSegment(start=0.0, end=1.0, text="第一句"),
                FiletransSegment(start=1.0, end=1.2, text="重叠噪点"),
                FiletransSegment(start=1.0, end=2.0, text="第二句"),
                FiletransSegment(start=1.8, end=2.4, text="第三句"),
            ]
        )

        self.assertEqual(
            cleaned,
            [
                FiletransSegment(start=0.0, end=1.0, text="第一句"),
                FiletransSegment(start=1.0, end=2.0, text="第二句"),
                FiletransSegment(start=2.0, end=2.4, text="第三句"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
