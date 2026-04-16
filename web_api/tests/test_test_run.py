from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from web_api.services.test import run_test


class TestRunDraftSyncTests(unittest.TestCase):
    def test_run_test_keeps_lines_draft_updated_from_asr_to_polish(self) -> None:
        raw_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "原始第一句",
                "optimized_text": "原始第一句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
        ]
        delete_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "原始第一句",
                "optimized_text": "原始第一句",
                "ai_suggest_remove": True,
                "user_final_remove": True,
            }
        ]
        polish_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "原始第一句",
                "optimized_text": "润色后的第一句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
        ]
        chapters = [
            {
                "chapter_id": 1,
                "title": "开场",
                "start": 0.0,
                "end": 1.0,
                "block_range": "1",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            input_dir = base_dir / "input"
            test_dir = base_dir / "test"
            input_dir.mkdir(parents=True, exist_ok=True)
            test_dir.mkdir(parents=True, exist_ok=True)

            srt_path = input_dir / "transcribed.srt"
            srt_path.write_text("placeholder", encoding="utf-8")
            optimized_srt_path = test_dir / "transcribed.optimized.srt"
            optimized_srt_path.write_text("placeholder", encoding="utf-8")
            optimized_srt_path.with_suffix(".test.txt").write_text(
                "\n".join(
                    [
                        "【00:00:00.000-00:00:01.000】润色后的第一句",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_run_auto_edit(source_srt, options, stage_callback=None, preview_callback=None):
                self.assertEqual(source_srt, srt_path)
                self.assertIsNotNone(stage_callback)
                self.assertIsNotNone(preview_callback)
                preview_callback(delete_lines)
                preview_callback(polish_lines)
                return SimpleNamespace(
                    optimized_srt_path=optimized_srt_path,
                    test_lines=polish_lines,
                    test_text_path=optimized_srt_path.with_suffix(".test.txt"),
                )

            with (
                patch(
                    "web_api.services.test.ensure_job_dirs",
                    return_value={
                        "base": base_dir,
                        "input": input_dir,
                        "test": test_dir,
                        "render": base_dir / "render",
                    },
                ),
                patch(
                    "web_api.services.test._load_required_paths",
                    return_value={"audio_path": str(input_dir / "audio.wav"), "video_path": str(input_dir / "video.mp4")},
                ),
                patch(
                    "web_api.services.test.build_pipeline_options",
                    return_value=SimpleNamespace(asr_backend="test", encoding="utf-8"),
                ),
                patch("web_api.services.test.get_job_owner_user_id", return_value="user-1"),
                patch("web_api.services.test.has_available_credits", return_value=True),
                patch(
                    "web_api.services.test.run_asr_transcription_stage",
                    return_value=SimpleNamespace(srt_path=srt_path, test_lines=raw_lines),
                ),
                patch("web_api.services.test.run_auto_edit", side_effect=fake_run_auto_edit),
                patch("web_api.services.test._upload_optimized_srt_to_oss", return_value=None),
                patch("web_api.services.test.generate_test_chapters", return_value=chapters),
                patch("web_api.services.test.replace_test_chapters"),
                patch("web_api.services.test.upsert_job_files"),
                patch("web_api.services.test.update_job"),
                patch("web_api.services.test.replace_test_lines") as mock_replace_test_lines,
            ):
                run_test("job-1")

        self.assertEqual(
            mock_replace_test_lines.call_args_list,
            [
                call("job-1", []),
                call("job-1", raw_lines),
                call("job-1", delete_lines),
                call("job-1", polish_lines),
                call("job-1", polish_lines),
            ],
        )


if __name__ == "__main__":
    unittest.main()
