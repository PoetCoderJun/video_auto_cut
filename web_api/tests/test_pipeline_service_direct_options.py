from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.shared.interfaces import PipelineOptions
from video_auto_cut.orchestration.pipeline_service import (
    run_auto_edit,
    run_transcribe,
)


class PipelineServiceDirectOptionsTests(unittest.TestCase):
    def test_run_transcribe_passes_pipeline_options_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "sample.wav"
            video_path.write_bytes(b"fake")
            srt_path = video_path.with_suffix(".srt")

            with patch("video_auto_cut.asr.transcribe.Transcribe") as mock_transcribe:
                mock_transcribe.return_value.run.side_effect = lambda: srt_path.write_text("", encoding="utf-8")
                result = run_transcribe(
                    video_path,
                    PipelineOptions(asr_dashscope_api_key="key"),
                    oss_object_key="oss-key",
                )

        self.assertEqual(result, srt_path)
        args, kwargs = mock_transcribe.call_args
        self.assertEqual(args[0], video_path)
        self.assertIsInstance(args[1], PipelineOptions)
        self.assertEqual(kwargs["oss_object_key"], "oss-key")

    def test_run_auto_edit_passes_pipeline_options_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            srt_path = Path(tmpdir) / "sample.srt"
            srt_path.write_text("", encoding="utf-8")
            optimized = srt_path.with_name("sample.optimized.srt")
            optimized.write_text("", encoding="utf-8")

            with patch("video_auto_cut.editing.auto_edit.AutoEdit") as mock_auto_edit:
                mock_auto_edit.from_pipeline_options.return_value.last_result = {
                    "test_lines": [{"line_id": 1, "start": 0.0, "end": 1.0, "original_text": "a", "optimized_text": "a", "ai_suggest_remove": False, "user_final_remove": False}],
                    "test_text_path": str(optimized.with_suffix(".test.txt")),
                }
                result = run_auto_edit(
                    srt_path,
                    PipelineOptions(llm_base_url="http://x", llm_model="m"),
                )

        args, kwargs = mock_auto_edit.from_pipeline_options.call_args
        self.assertEqual(args[0], srt_path)
        self.assertIsInstance(args[1], PipelineOptions)
        self.assertEqual(result.test_text_path, optimized.with_suffix(".test.txt"))

if __name__ == "__main__":
    unittest.main()
