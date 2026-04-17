from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from video_auto_cut.asr.transcribe_stage import main


class AsrTranscribeStageCliTests(unittest.TestCase):
    def test_main_writes_test_text_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            media_path = Path(tmpdir) / "sample.wav"
            media_path.write_bytes(b"fake")
            srt_path = Path(tmpdir) / "sample.srt"
            srt_path.write_text("", encoding="utf-8")
            options = SimpleNamespace(encoding="utf-8")
            artifacts = SimpleNamespace(
                media_path=media_path,
                srt_path=srt_path,
                test_lines=[
                    {
                        "line_id": 1,
                        "start": 0.0,
                        "end": 1.0,
                        "original_text": "原文",
                        "optimized_text": "原文",
                        "ai_suggest_remove": False,
                        "user_final_remove": False,
                    }
                ],
            )
            stdout = io.StringIO()
            with patch("video_auto_cut.asr.transcribe_stage.build_pipeline_options_from_env", return_value=options), patch(
                "video_auto_cut.asr.transcribe_stage.run_asr_transcription_stage", return_value=artifacts
            ):
                with redirect_stdout(stdout):
                    exit_code = main(["--input", str(media_path)])

            self.assertEqual(exit_code, 0)
            test_text_path = media_path.with_suffix(".test.txt").resolve()
            payload = test_text_path.read_text(encoding="utf-8")
            self.assertIn("【00:00:00.000-00:00:01.000】原文", payload)

            cli_payload = json.loads(stdout.getvalue())
            self.assertEqual(cli_payload["test_text_path"], str(test_text_path))
            self.assertEqual(cli_payload["line_count"], 1)


if __name__ == "__main__":
    unittest.main()
