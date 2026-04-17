from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from video_auto_cut.asr.transcribe import Transcribe


class TranscribeRunTests(unittest.TestCase):
    def _make_args(self, input_path: Path, *, force: bool) -> SimpleNamespace:
        return SimpleNamespace(
            inputs=[str(input_path)],
            force=force,
            encoding="utf-8",
            lang=None,
            prompt="",
            oss_object_key=None,
            asr_progress_callback=None,
            asr_backend="dashscope_filetrans",
        )

    def test_run_skips_existing_srt_when_force_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "sample.wav"
            media_path.write_bytes(b"fake")
            srt_path = media_path.with_suffix(".srt")
            srt_path.write_text("keep me", encoding="utf-8")

            with patch.object(Transcribe, "_init_dashscope_filetrans", autospec=True, return_value=None), patch.object(
                Transcribe,
                "_dashscope_filetrans_transcribe",
                autospec=True,
                side_effect=AssertionError("should skip when SRT already exists"),
            ):
                Transcribe(self._make_args(media_path, force=False)).run()

            self.assertEqual(srt_path.read_text(encoding="utf-8"), "keep me")

    def test_run_overwrites_existing_srt_when_force_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "sample.wav"
            media_path.write_bytes(b"fake")
            srt_path = media_path.with_suffix(".srt")
            srt_path.write_text("old content", encoding="utf-8")

            with patch.object(Transcribe, "_init_dashscope_filetrans", autospec=True, return_value=None), patch.object(
                Transcribe,
                "_dashscope_filetrans_transcribe",
                autospec=True,
                return_value=([{"start": 0.0, "end": 1.0, "text": "新的字幕"}], None),
            ) as mock_transcribe:
                Transcribe(self._make_args(media_path, force=True)).run()

            self.assertEqual(mock_transcribe.call_count, 1)
            output = srt_path.read_text(encoding="utf-8")
            self.assertIn("新的字幕", output)
            self.assertNotIn("old content", output)

    def test_run_writes_word_timing_sidecar_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "sample.wav"
            media_path.write_bytes(b"fake")
            srt_path = media_path.with_suffix(".srt")
            sidecar_path = media_path.with_suffix(".asr.words.json")
            sidecar_payload = {
                "version": 1,
                "source": "dashscope",
                "asset_id": "sample.wav",
                "language": "zh",
                "created_at": "2026-04-17T00:00:00Z",
                "audio": {"duration_ms": 1000},
                "words": [{"index": 0, "text": "新", "start_ms": 0, "end_ms": 500, "speaker": None, "confidence": None, "punct": ""}],
                "sentences": [],
                "meta": {"upstream_task_id": "task-1", "schema_note": "raw word timings sidecar"},
            }

            with patch.object(Transcribe, "_init_dashscope_filetrans", autospec=True, return_value=None), patch.object(
                Transcribe,
                "_dashscope_filetrans_transcribe",
                autospec=True,
                return_value=([{"start": 0.0, "end": 1.0, "text": "新的字幕"}], sidecar_payload),
            ):
                Transcribe(self._make_args(media_path, force=True)).run()

            self.assertTrue(srt_path.exists())
            self.assertTrue(sidecar_path.exists())
            self.assertIn("\"words\"", sidecar_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
